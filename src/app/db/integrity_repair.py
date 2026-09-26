"""Deterministic SQLite repair plan. No guessing owners; no sync replay.

Original rows are private DB archive records, never included in console reports.
All writes, Alembic adoption, constraints and the head marker share one transaction.
"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import sqlite3


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      default=lambda value: {'bytes_hex': value.hex()})


def fingerprint(db):
    digest = hashlib.sha256()
    for row in db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"):
        digest.update(encoded(tuple(row)).encode())
    for name, sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        digest.update(encoded([name, sql]).encode())
        rows = sorted(encoded(tuple(row)) for row in db.execute(f'SELECT * FROM {quote(name)}'))
        for row in rows: digest.update(row.encode())
    return digest.hexdigest()


def row_data(db, table, identifier):
    cursor = db.execute(f'SELECT * FROM {quote(table)} WHERE id=?', (identifier,))
    row = cursor.fetchone()
    return dict(zip([c[0] for c in cursor.description], row)) if row else None


def plan_repair(db):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    counts = {t: db.execute(f'SELECT count(*) FROM {quote(t)}').fetchone()[0] for t in sorted(tables)}
    planned, ambiguous = {}, []
    violations = list(db.execute('PRAGMA foreign_key_check'))
    references = set()
    for table, rowid, parent, fk_id in violations:
        fk = next(r for r in db.execute(f'PRAGMA foreign_key_list({quote(table)})') if r[0] == fk_id)
        references.add((table, rowid, fk[3]))
    # Old manual schemas did not declare every intended FK. Check those before
    # installing constraints too, without first mutating/adopting the database.
    from app.db.migration_steps import metadata
    for table in metadata().tables.values():
        if table.name not in tables:
            continue
        present = {r[1] for r in db.execute(f'PRAGMA table_info({quote(table.name)})')}
        for fk in table.foreign_keys:
            if fk.parent.name not in present or fk.column.table.name not in tables:
                continue
            field = quote(fk.parent.name)
            query = (f'SELECT c.rowid FROM {quote(table.name)} c WHERE c.{field} IS NOT NULL AND NOT EXISTS '
                     f'(SELECT 1 FROM {quote(fk.column.table.name)} p WHERE p.{quote(fk.column.name)}=c.{field})')
            references.update((table.name, row[0], fk.parent.name) for row in db.execute(query))
    for table, rowid, field in sorted(references):
        cursor = db.execute(f'SELECT * FROM {quote(table)} WHERE rowid=?', (rowid,))
        row = dict(zip([c[0] for c in cursor.description], cursor.fetchone()))
        identifier = row.get('id')
        item = {'table': table, 'id': identifier, 'category': 'LEGACY_QUARANTINE',
                'action': 'archive_and_detach', 'columns': [], 'reason': 'missing_reference'}
        if table == 'refresh_tokens' and field == 'user_id':
            item.update(category='SAFE_TO_REMOVE', action='archive_and_remove', reason='session_owner_missing')
        elif table == 'audit_logs' and field == 'user_id':
            item['columns'] = [field]
        elif table == 'sync_outbox' and field in ('user_id', 'note_id') and row.get('protocol_version') in (None, 0):
            item['columns'] = [field]
        else:
            ambiguous.append({'table': table, 'id': identifier, 'column': field, 'reason': 'unclassified_foreign_key'})
            continue
        key = (table, identifier)
        if key in planned:
            item['columns'] = sorted(set(item['columns'] + planned[key]['columns']))
        planned[key] = item
    cross = []
    if {'users', 'notes', 'files', 'note_links'} <= tables:
        for table in ('notes', 'files'):
            for identifier, in db.execute(f'SELECT id FROM {table} x WHERE user_id IS NULL OR NOT EXISTS '
                                         '(SELECT 1 FROM users u WHERE u.id=x.user_id)'):
                ambiguous.append({'table': table, 'id': identifier, 'reason': 'orphan_owner'})
        for identifier, in db.execute('SELECT f.id FROM files f JOIN notes n ON n.id=f.note_id '
            'WHERE f.user_id IS NULL OR n.user_id IS NULL OR f.user_id<>n.user_id'):
            ambiguous.append({'table': 'files', 'id': identifier, 'reason': 'cross_owner_parent'})
        cross = [dict(id=r[0], source_owner=r[1], target_owner=r[2]) for r in db.execute(
            'SELECT l.id,a.user_id,b.user_id FROM note_links l JOIN notes a ON a.id=l.from_id '
            'JOIN notes b ON b.id=l.to_id WHERE a.user_id IS NULL OR b.user_id IS NULL OR a.user_id<>b.user_id ORDER BY l.id')]
        for link in cross:
            if link['source_owner'] is None or link['target_owner'] is None:
                ambiguous.append({'table': 'note_links', 'id': link['id'], 'reason': 'unknown_link_owner'})
            else:
                planned[('note_links', link['id'])] = {'table': 'note_links', 'id': link['id'],
                    'category': 'LEGACY_QUARANTINE', 'action': 'archive_and_remove', 'columns': [], 'reason': 'cross_owner_link'}
    actions = [planned[key] for key in sorted(planned)]
    predicted = dict(counts)
    predicted['integrity_archive'] = predicted.get('integrity_archive', 0) + len(actions)
    for item in actions:
        if item['action'] == 'archive_and_remove': predicted[item['table']] -= 1
    legacy = 0
    if 'sync_outbox' in tables:
        columns = {r[1] for r in db.execute('PRAGMA table_info(sync_outbox)')}
        where = ' WHERE protocol_version=0 OR protocol_version IS NULL' if 'protocol_version' in columns else ''
        legacy = db.execute('SELECT count(*) FROM sync_outbox' + where).fetchone()[0]
    return {'version': 1, 'fingerprint': fingerprint(db), 'foreign_key_violations': len(violations),
            'canonical_reference_violations': len(references),
            'actions': actions, 'ambiguous': ambiguous, 'cross_owner_links': cross,
            'counts_before': counts, 'predicted_data_counts': predicted,
            'legacy_quarantined': legacy, 'auto_sendable_legacy': 0}


def read_plan(database):
    with sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True) as db:
        return plan_repair(db)


def apply_repair(database, expected, backup):
    # Import the backup verifier, not application startup/config.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
    from local_data import digest, verify_checksums
    database, backup = Path(database).resolve(), Path(backup).resolve()
    manifest_path = backup / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    verified = json.loads((backup / 'VERIFIED.json').read_text())
    if Path(manifest['database']).resolve() != database or verified['manifestSHA256'] != digest(manifest_path):
        raise ValueError('Backup is not a verified recovery point for this database')
    verify_checksums(backup, manifest)
    with sqlite3.connect((backup / 'database.sqlite3').as_uri() + '?mode=ro', uri=True) as saved:
        if fingerprint(saved) != expected['fingerprint']:
            raise ValueError('Plan does not match the verified backup')
    from app.db.engine import make_engine
    from app.db.migrate import migration_connection, upgrade_connection, BASELINE_REVISION
    engine = make_engine('sqlite:///' + str(database))
    try:
        with migration_connection(engine) as connection:
            db = connection.connection.driver_connection
            actual = plan_repair(db)
            if actual != expected or actual['ambiguous']:
                raise ValueError('Stale or ambiguous repair plan; no changes applied')
            originals = {(a['table'], a['id']): row_data(db, a['table'], a['id']) for a in actual['actions']}
            upgrade_connection(connection, BASELINE_REVISION)
            for action in actual['actions']:
                table, identifier = action['table'], action['id']
                original = encoded(originals[(table, identifier)])
                archive_id = hashlib.sha256((table + '/' + identifier + '/' + original).encode()).hexdigest()
                db.execute('INSERT INTO integrity_archive (id,repair_id,source_table,source_id,category,reason,original_json,created_at) '
                           'VALUES (?,?,?,?,?,?,?,?)', (archive_id, expected['fingerprint'], table, identifier,
                            action['category'], action['reason'], original, dt.datetime.utcnow().isoformat()))
                if action['action'] == 'archive_and_remove':
                    db.execute(f'DELETE FROM {quote(table)} WHERE id=?', (identifier,))
                else:
                    changes = ','.join(quote(c) + '=NULL' for c in action['columns'])
                    db.execute(f'UPDATE {quote(table)} SET {changes} WHERE id=?', (identifier,))
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Repair left FK violations; rolling back')
            upgrade_connection(connection)
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Repair quick_check failed; rolling back')
            result = plan_repair(db)
            if result['ambiguous'] or result['foreign_key_violations'] or result['cross_owner_links']:
                raise RuntimeError('Repair validation failed; rolling back')
            if result['legacy_quarantined'] != actual['legacy_quarantined']:
                raise RuntimeError('Legacy quarantine changed; rolling back')
        return {'applied': True, 'repair_id': expected['fingerprint'], 'archived_rows': len(actual['actions']),
                'quick_check': 'ok', 'foreign_key_violations': 0, 'counts_after': result['counts_before'],
                'legacy_quarantined': result['legacy_quarantined'], 'auto_sendable_legacy': 0}
    finally:
        engine.dispose()
