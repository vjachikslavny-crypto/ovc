#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sqlite3
from pathlib import Path
from typing import Dict, Optional


def _normalize(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip().lower()
    return v or None


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def _insert_row(conn: sqlite3.Connection, table: str, row: dict, target_columns: list[str]) -> bool:
    payload = {k: row[k] for k in target_columns if k in row}
    cols = list(payload.keys())
    values = [payload[c] for c in cols]
    placeholders = ", ".join(["?"] * len(cols))
    col_sql = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
    try:
        conn.execute(sql, values)
        return True
    except sqlite3.IntegrityError:
        return False


def _ensure_unique_username(conn: sqlite3.Connection, base: str) -> str:
    candidate = base
    suffix = 1
    while conn.execute("SELECT 1 FROM users WHERE lower(username)=lower(?)", (candidate,)).fetchone():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def migrate(source_db: Path, target_db: Path, backup: bool = True) -> dict:
    if not source_db.exists():
        raise FileNotFoundError(f"source db not found: {source_db}")
    if not target_db.exists():
        raise FileNotFoundError(f"target db not found: {target_db}")

    if backup:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = target_db.with_name(f"{target_db.name}.bak.{stamp}")
        shutil.copy2(target_db, backup_path)

    source = sqlite3.connect(source_db)
    source.row_factory = sqlite3.Row

    target = sqlite3.connect(target_db)
    target.row_factory = sqlite3.Row
    target.execute("PRAGMA foreign_keys = OFF")

    stats = {
        "users_inserted": 0,
        "users_mapped": 0,
        "notes_inserted": 0,
        "files_inserted": 0,
        "chunks_inserted": 0,
        "links_inserted": 0,
        "tags_inserted": 0,
    }

    user_map: Dict[str, str] = {}

    try:
        with target:
            # Build target user indexes
            users_by_email: Dict[str, str] = {}
            users_by_username: Dict[str, str] = {}
            users_by_id: Dict[str, str] = {}
            for row in target.execute("SELECT id, username, email FROM users"):
                rid = row["id"]
                users_by_id[rid] = rid
                em = _normalize(row["email"])
                un = _normalize(row["username"])
                if em:
                    users_by_email[em] = rid
                if un:
                    users_by_username[un] = rid

            user_cols = _table_columns(target, "users")

            # 1) migrate users with merge/mapping rules
            for row in source.execute("SELECT * FROM users"):
                r = _row_to_dict(row)
                old_id = r["id"]
                email_norm = _normalize(r.get("email"))
                user_norm = _normalize(r.get("username"))

                mapped = users_by_id.get(old_id)
                if not mapped and email_norm:
                    mapped = users_by_email.get(email_norm)
                if not mapped and user_norm:
                    mapped = users_by_username.get(user_norm)

                if mapped:
                    user_map[old_id] = mapped
                    stats["users_mapped"] += 1
                    continue

                base_username = r.get("username") or (email_norm.split("@")[0] if email_norm else f"user_{old_id[:8]}")
                base_username = base_username.replace(" ", "_")
                username = _ensure_unique_username(target, base_username)

                email = r.get("email")
                if email and _normalize(email) in users_by_email:
                    email = None

                insert_row = dict(r)
                insert_row["username"] = username
                insert_row["email"] = email

                ok = _insert_row(target, "users", insert_row, user_cols)
                if not ok:
                    # fallback: try with generated id + stripped optional fields
                    new_id = f"migr_{old_id}"
                    insert_row["id"] = new_id
                    insert_row["email"] = None
                    insert_row["supabase_id"] = None
                    username2 = _ensure_unique_username(target, username)
                    insert_row["username"] = username2
                    ok = _insert_row(target, "users", insert_row, user_cols)
                    if not ok:
                        continue
                    user_map[old_id] = new_id
                    users_by_id[new_id] = new_id
                    users_by_username[_normalize(username2)] = new_id
                    stats["users_inserted"] += 1
                    continue

                new_id = insert_row["id"]
                user_map[old_id] = new_id
                users_by_id[new_id] = new_id
                users_by_username[_normalize(username)] = new_id
                if email:
                    users_by_email[_normalize(email)] = new_id
                stats["users_inserted"] += 1

            # 2) notes
            note_cols = _table_columns(target, "notes")
            for row in source.execute("SELECT * FROM notes"):
                r = _row_to_dict(row)
                if target.execute("SELECT 1 FROM notes WHERE id=?", (r["id"],)).fetchone():
                    continue
                uid = r.get("user_id")
                if uid:
                    r["user_id"] = user_map.get(uid, uid)
                if r.get("user_id") and not target.execute("SELECT 1 FROM users WHERE id=?", (r["user_id"],)).fetchone():
                    r["user_id"] = None
                if _insert_row(target, "notes", r, note_cols):
                    stats["notes_inserted"] += 1

            # 3) note chunks
            chunk_cols = _table_columns(target, "note_chunks")
            for row in source.execute("SELECT * FROM note_chunks"):
                r = _row_to_dict(row)
                if target.execute("SELECT 1 FROM note_chunks WHERE id=?", (r["id"],)).fetchone():
                    continue
                if not target.execute("SELECT 1 FROM notes WHERE id=?", (r.get("note_id"),)).fetchone():
                    continue
                if _insert_row(target, "note_chunks", r, chunk_cols):
                    stats["chunks_inserted"] += 1

            # 4) files
            file_cols = _table_columns(target, "files")
            for row in source.execute("SELECT * FROM files"):
                r = _row_to_dict(row)
                if target.execute("SELECT 1 FROM files WHERE id=?", (r["id"],)).fetchone():
                    continue
                uid = r.get("user_id")
                if uid:
                    r["user_id"] = user_map.get(uid, uid)
                if r.get("user_id") and not target.execute("SELECT 1 FROM users WHERE id=?", (r["user_id"],)).fetchone():
                    r["user_id"] = None
                nid = r.get("note_id")
                if nid and not target.execute("SELECT 1 FROM notes WHERE id=?", (nid,)).fetchone():
                    r["note_id"] = None
                if _insert_row(target, "files", r, file_cols):
                    stats["files_inserted"] += 1

            # 5) links
            link_cols = _table_columns(target, "note_links")
            for row in source.execute("SELECT * FROM note_links"):
                r = _row_to_dict(row)
                if target.execute("SELECT 1 FROM note_links WHERE id=?", (r["id"],)).fetchone():
                    continue
                if not target.execute("SELECT 1 FROM notes WHERE id=?", (r.get("from_id"),)).fetchone():
                    continue
                if not target.execute("SELECT 1 FROM notes WHERE id=?", (r.get("to_id"),)).fetchone():
                    continue
                if _insert_row(target, "note_links", r, link_cols):
                    stats["links_inserted"] += 1

            # 6) tags
            tag_cols = _table_columns(target, "note_tags")
            for row in source.execute("SELECT * FROM note_tags"):
                r = _row_to_dict(row)
                if target.execute("SELECT 1 FROM note_tags WHERE id=?", (r["id"],)).fetchone():
                    continue
                if not target.execute("SELECT 1 FROM notes WHERE id=?", (r.get("note_id"),)).fetchone():
                    continue
                if _insert_row(target, "note_tags", r, tag_cols):
                    stats["tags_inserted"] += 1

        return stats
    finally:
        source.close()
        target.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate old desktop DB into shared OVC DB")
    parser.add_argument(
        "--source",
        default=str(Path.home() / "Library/Application Support/com.ovc.desktop/ovc-desktop.db"),
    )
    parser.add_argument("--target", default="src/ovc.db")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    target = Path(args.target).expanduser().resolve()

    stats = migrate(source, target, backup=not args.no_backup)
    print("Migration completed")
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
