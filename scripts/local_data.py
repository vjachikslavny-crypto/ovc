#!/usr/bin/env python3
"""SQLite backup/isolated restore verification. Never imports application startup."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TABLES = ("users", "notes", "files", "note_links", "note_tags", "sync_outbox")


def current_paths():
    from app.core.config import settings
    from sqlalchemy.engine import make_url
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("This command requires an existing file-backed SQLite database")
    db = Path(url.database).expanduser().resolve()
    configured = os.getenv("OVC_UPLOAD_ROOT", "").strip()
    legacy = Path.home() / "data" / "uploads"
    storage = Path(configured).expanduser().resolve() if configured else (legacy if legacy.exists() else ROOT / "data" / "uploads")
    return db, storage


def readonly(db):
    return sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)


def counts(conn, selected=None):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    return {t: conn.execute('SELECT count(*) FROM "' + t.replace('"', '""') + '"').fetchone()[0]
            if t in tables else None for t in sorted(selected or tables)}


def schema_state(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    revisions = [r[0] for r in conn.execute('SELECT version_num FROM alembic_version ORDER BY version_num')] if 'alembic_version' in tables else []
    violations = len(list(conn.execute('PRAGMA foreign_key_check')))
    from app.db.migrate import EXPECTED_DB_REVISION
    if revisions == [EXPECTED_DB_REVISION] and violations:
        raise RuntimeError('Database claims migration head but has FK violations')
    return {'revisions': revisions, 'foreignKeyViolations': violations}


def stored_paths(conn):
    columns = [r[1] for r in conn.execute("PRAGMA table_info(files)") if r[1].startswith("path_")]
    return sorted({str(Path(row[0]).expanduser().resolve()) for col in columns
                   for row in conn.execute(f'SELECT "{col}" FROM files WHERE "{col}" IS NOT NULL') if row[0]})


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_tree(source, target):
    if source.is_symlink():
        raise RuntimeError(f"Symlink requires explicit review: {source}")
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in sorted(source.iterdir()):
            copy_tree(child, target / child.name)
    elif source.is_file():
        # Config/secrets are intentionally not part of a storage backup.
        if source.name.startswith('.env') or source.suffix in {'.pem', '.key'}:
            raise RuntimeError(f"Secret-like file in storage; separate it before backup: {source}")
        before = source.stat()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or digest(source) != digest(target):
            raise RuntimeError(f"File changed during backup: {source}; stop writers and retry")
    else:
        raise RuntimeError(f"Missing/non-regular path: {source}")


def backup(destination):
    db, storage = current_paths()
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    if destination.is_relative_to(storage.resolve()):
        raise RuntimeError("Backup destination must be outside storage")
    with readonly(db) as source:
        version = source.execute("PRAGMA data_version").fetchone()[0]
        with sqlite3.connect(destination / "database.sqlite3") as target:
            source.backup(target)
            snapshot_counts = counts(target)
            snapshot_schema = schema_state(target)
            paths = stored_paths(target)
            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite backup quick_check failed")
        roots = []
        if storage.exists():
            roots.append(storage.resolve())
        for value in paths:
            path = Path(value)
            if not path.exists():
                raise RuntimeError(f"Referenced asset is missing: {path}")
            if not any(path == root or root in path.parents for root in roots):
                roots.append(path)
        mappings = []
        for i, root in enumerate(roots):
            relative = f"storage/{i}"
            copy_tree(root, destination / relative)
            mappings.append({"source": str(root), "backup": relative})
        if source.execute("PRAGMA data_version").fetchone()[0] != version:
            raise RuntimeError("Database changed during backup; stop writers and retry (backup not verified)")
    checksums = {str(p.relative_to(destination)): digest(p) for p in sorted(destination.rglob('*')) if p.is_file()}
    manifest = {"createdAt": dt.datetime.now(dt.timezone.utc).isoformat(), "database": str(db),
                "storage": str(storage), "counts": snapshot_counts, "paths": paths,
                "mappings": mappings, "sha256": checksums, "schema": snapshot_schema}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({"backup": str(destination), "sourceDatabase": str(db), "copiedRoots": mappings,
                      "counts": snapshot_counts, "files": len(checksums), "secrets": "env/key files excluded; DB contains private application data"}, ensure_ascii=False, indent=2))


def mapped_path(value, manifest, restored):
    path = Path(value)
    for mapping in manifest['mappings']:
        source = Path(mapping['source'])
        if path == source or source in path.parents:
            return checked_path(restored, mapping['backup']) / path.relative_to(source)
    raise RuntimeError(f"Unmapped stored path: {path}")


def checked_path(root, relative):
    relative = Path(relative)
    path = root / relative
    if relative.is_absolute() or '..' in relative.parts or not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError('Invalid backup-relative path')
    return path


def verify_checksums(root, manifest):
    if 'database.sqlite3' not in manifest['sha256']:
        raise RuntimeError('Backup manifest has no database checksum')
    if any(path.is_symlink() for path in root.rglob('*')):
        raise RuntimeError('Backup must not contain symlinks')
    for relative, checksum in manifest['sha256'].items():
        if digest(checked_path(root, relative)) != checksum:
            raise RuntimeError(f'Backup checksum mismatch: {relative}')


def verify(backup_dir):
    # A failed recheck must invalidate an earlier successful verification.
    (backup_dir / 'VERIFIED.json').unlink(missing_ok=True)
    manifest_path = backup_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    verify_checksums(backup_dir, manifest)
    with tempfile.TemporaryDirectory(prefix='ovc-restore-check-') as tmp:
        restored = Path(tmp) / 'restore'
        shutil.copytree(backup_dir, restored)
        verify_checksums(restored, manifest)
        with sqlite3.connect(restored / 'database.sqlite3') as conn:
            if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Restore quick_check failed')
            if counts(conn, manifest['counts']) != manifest['counts']:
                raise RuntimeError('Entity counts differ from source snapshot')
            restored_schema = schema_state(conn)
            if 'schema' in manifest and restored_schema != manifest['schema']:
                raise RuntimeError('Restored schema revision/FK state differs from snapshot')
            # Rebase only the disposable restored DB, never working data.
            columns = [r[1] for r in conn.execute('PRAGMA table_info(files)') if r[1].startswith('path_')]
            for col in columns:
                for file_id, value in conn.execute(f'SELECT id,"{col}" FROM files WHERE "{col}" IS NOT NULL').fetchall():
                    if not value:
                        continue
                    path = mapped_path(str(Path(value).resolve()), manifest, restored)
                    if not path.exists():
                        raise RuntimeError(f'Missing restored asset in {col}')
                    conn.execute(f'UPDATE files SET "{col}"=? WHERE id=?', (str(path), file_id))
            violations = len(list(conn.execute('PRAGMA foreign_key_check')))
        with readonly(Path(manifest['database'])) as source:
            current_counts = counts(source, manifest['counts'])
        print(json.dumps({"verified": True, "isolatedRestore": str(restored), "quick_check": "ok",
                          "snapshotCounts": manifest['counts'], "currentSourceCounts": current_counts,
                          "sourceCountsChangedSinceBackup": current_counts != manifest['counts'],
                          "schema": restored_schema, "existingFKWarnings": violations,
                          "storedPathsChecked": len(manifest['paths'])}, ensure_ascii=False, indent=2))
    (backup_dir / 'VERIFIED.json').write_text(json.dumps({"manifestSHA256": digest(manifest_path), "verifiedAt": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=2) + '\n')


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'verify'])
    parser.add_argument('directory', nargs='?', type=Path)
    args = parser.parse_args()
    directory = args.directory or ROOT / 'data' / 'backups' / dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    if args.operation == 'verify' and args.directory is None:
        parser.error('verify requires an existing backup directory')
    try:
        (backup if args.operation == 'backup' else verify)(directory.resolve())
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
