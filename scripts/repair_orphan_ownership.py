#!/usr/bin/env python3
"""Explicit administrative orphan assignment; dry-run unless --apply is supplied.

Plan: {"user_id": "...", "note_ids": ["..."], "file_ids": ["..."]}.
Never reassigns existing owners, deletes records, or guesses from email.
"""
import argparse
import json
from pathlib import Path
import sqlite3

from local_data import current_paths, readonly, digest, verify_checksums


def validate(db, plan):
    uid = plan['user_id']
    if not db.execute('SELECT 1 FROM users WHERE id=? AND is_active=1', (uid,)).fetchone():
        raise ValueError('Target must be an active existing user')
    note_ids, file_ids = set(plan.get('note_ids', [])), set(plan.get('file_ids', []))
    if not note_ids and not file_ids:
        raise ValueError('Plan has no explicit objects')
    for table, identifiers in [('notes', note_ids), ('files', file_ids)]:
        for identifier in identifiers:
            row = db.execute(f'SELECT user_id FROM {table} WHERE id=?', (identifier,)).fetchone()
            if row is None or row[0] is not None:
                raise ValueError(f'{table}/{identifier} is missing or already owned')
    for nid in note_ids:
        # Every surviving link and attached file must remain in the same context.
        for other, in db.execute('SELECT to_id FROM note_links WHERE from_id=? UNION SELECT from_id FROM note_links WHERE to_id=?', (nid, nid)):
            row = db.execute('SELECT user_id FROM notes WHERE id=?', (other,)).fetchone()
            if other not in note_ids and (not row or row[0] != uid):
                raise ValueError('Plan would leave a cross-owner/orphan link')
        for fid, owner in db.execute('SELECT id,user_id FROM files WHERE note_id=?', (nid,)):
            if fid not in file_ids and owner != uid:
                raise ValueError('Plan must include attached orphan files')
    for fid in file_ids:
        nid, = db.execute('SELECT note_id FROM files WHERE id=?', (fid,)).fetchone()
        if nid and nid not in note_ids:
            row = db.execute('SELECT user_id FROM notes WHERE id=?', (nid,)).fetchone()
            if not row or row[0] != uid:
                raise ValueError('File note is missing or belongs to another owner')
    return uid, note_ids, file_ids


def repair(database, plan, *, apply=False, backup=None):
    database = Path(database).resolve()
    with readonly(database) as db:
        uid, note_ids, file_ids = validate(db, plan)
    if apply:
        if backup is None:
            raise ValueError('--apply requires --backup with a verified recovery point')
        manifest_file = backup / 'manifest.json'
        manifest = json.loads(manifest_file.read_text())
        verified = json.loads((backup / 'VERIFIED.json').read_text())
        if (Path(manifest['database']).resolve() != database or
                verified['manifestSHA256'] != digest(manifest_file) or
                manifest['sha256']['database.sqlite3'] != digest(backup / 'database.sqlite3')):
            raise ValueError('Backup does not match the database or verification marker')
        verify_checksums(backup, manifest)
        with sqlite3.connect(database) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            uid, note_ids, file_ids = validate(db, plan)
            for table, identifiers in [('notes', note_ids), ('files', file_ids)]:
                for identifier in identifiers:
                    db.execute(f'UPDATE {table} SET user_id=? WHERE id=? AND user_id IS NULL', (uid, identifier))
    return {'applied': apply, 'user_id': uid, 'note_ids': sorted(note_ids), 'file_ids': sorted(file_ids)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('plan', type=Path)
    p.add_argument('--database', type=Path)
    p.add_argument('--backup', type=Path)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    print(json.dumps(repair(args.database or current_paths()[0], json.loads(args.plan.read_text()),
                            apply=args.apply, backup=args.backup), indent=2))
