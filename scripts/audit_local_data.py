#!/usr/bin/env python3
"""Read-only block compatibility and ownership audit. Prints IDs/counts, never content or tokens."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from local_data import current_paths, readonly
from app.agent.block_models import normalize_blocks
from pydantic import ValidationError


def audit(path):
    with readonly(path) as db:
        def ids(sql):
            return [row[0] for row in db.execute(sql)]
        report = {
            "database": str(path),
            "quick_check": db.execute("PRAGMA quick_check").fetchone()[0],
            "notes_without_valid_owner": ids("SELECT n.id FROM notes n LEFT JOIN users u ON n.user_id=u.id WHERE u.id IS NULL"),
            "files_without_valid_owner": ids("SELECT f.id FROM files f LEFT JOIN users u ON f.user_id=u.id WHERE u.id IS NULL"),
            "files_with_missing_note": ids("SELECT f.id FROM files f LEFT JOIN notes n ON f.note_id=n.id WHERE f.note_id IS NOT NULL AND n.id IS NULL"),
            "files_with_different_note_owner": ids("SELECT f.id FROM files f JOIN notes n ON f.note_id=n.id WHERE f.user_id IS NOT n.user_id"),
            "unattached_files": ids("SELECT id FROM files WHERE note_id IS NULL"),
            "cross_owner_links": ids("SELECT l.id FROM note_links l JOIN notes a ON l.from_id=a.id JOIN notes b ON l.to_id=b.id WHERE a.user_id IS NOT b.user_id"),
            "refresh_tokens_missing_user": ids("SELECT t.id FROM refresh_tokens t LEFT JOIN users u ON t.user_id=u.id WHERE u.id IS NULL"),
            "audit_logs_missing_user": ids("SELECT a.id FROM audit_logs a LEFT JOIN users u ON a.user_id=u.id WHERE a.user_id IS NOT NULL AND u.id IS NULL"),
            "duplicate_supabase_mapping_groups": db.execute("SELECT count(*) FROM (SELECT supabase_id FROM users WHERE supabase_id IS NOT NULL GROUP BY supabase_id HAVING count(*) > 1)").fetchone()[0],
            "conflicting_email_mapping_groups": db.execute("SELECT count(*) FROM (SELECT lower(trim(email)) FROM users WHERE email IS NOT NULL GROUP BY lower(trim(email)) HAVING count(distinct supabase_id)>1)").fetchone()[0],
        }
        report["foreign_key_violations"] = dict(Counter(row[0] for row in db.execute("PRAGMA foreign_key_check")))
        compatibility = {"valid": 0, "normalized": 0, "unsupported": []}
        for note_id, raw in db.execute("SELECT id,blocks_json FROM notes"):
            try:
                blocks = json.loads(raw or "[]")
                normalized = normalize_blocks(blocks)
                compatibility["valid" if normalized == blocks else "normalized"] += 1
            except (ValidationError, ValueError, TypeError):
                compatibility["unsupported"].append(note_id)
        report["blocks"] = compatibility
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.database or current_paths()[0]), ensure_ascii=False, indent=2))
