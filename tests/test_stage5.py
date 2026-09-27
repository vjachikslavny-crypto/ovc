"""Migration/repair invariants. Working data and production services are never used."""
from pathlib import Path
import json
import sqlite3
import sys

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient

from app.db import session as db
from app.db.engine import make_engine
from app.db.migrate import upgrade, EXPECTED_DB_REVISION, migration_connection
from app.db.migration_steps import metadata
from app.db.integrity_repair import read_plan, apply_repair, fingerprint
from app.db.readiness import status
from app.db.models import Note, NoteLink, NoteTag, FileAsset, SyncOutbox, SyncConflict
from app.models.user import User
from app.models.session import RefreshToken
from app.models.audit import AuditLog
from app.main import app
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import local_data


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    database = tmp_path / 'old.db'
    uploads = tmp_path / 'uploads'; uploads.mkdir()
    (uploads / 'keep.md').write_text('# keep bytes')
    with sqlite3.connect(database) as conn:
        conn.executescript((Path(__file__).parent / 'fixtures/stage5_legacy_schema.sql').read_text())
        for uid in ('a', 'b'):
            conn.execute("INSERT INTO users(id,username,password_hash,created_at,updated_at,is_active,role,failed_login_count) VALUES (?,?, 'unused',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1,'user',0)", (uid, uid))
            conn.execute("INSERT INTO notes(id,user_id,title,style_theme,layout_hints,blocks_json,passport_json,created_at,updated_at,revision,tombstone) VALUES (?,?,'keep','dark','{}','[]','{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,7,0)", ('n-'+uid,uid))
        conn.execute("INSERT INTO files(id,note_id,user_id,kind,mime,filename,size,path_original,created_at) VALUES ('f','n-a','a','markdown','text/markdown','keep.md',12,?,CURRENT_TIMESTAMP)", (str(uploads/'keep.md'),))
        conn.execute("INSERT INTO note_links(id,from_id,to_id,reason,created_at) VALUES ('bad-link','n-a','n-b','historical',CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO refresh_tokens(id,user_id,token_hash,created_at,expires_at) VALUES ('bad-session','gone','private-token-hash',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO audit_logs(id,user_id,event,metadata,created_at) VALUES ('bad-audit','gone','old','{\"private\":true}',CURRENT_TIMESTAMP)")
        for n in range(187):
            conn.execute("INSERT INTO sync_outbox(id,user_id,note_id,op_type,payload_json,status,tries,created_at,updated_at) VALUES (?,?,?,'update_note',?,'pending',9,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", (str(n), 'gone' if n==0 else 'a', 'missing' if n<2 else 'n-a', ' {"historical":true} '))
    monkeypatch.setattr(local_data, 'current_paths', lambda: (database, uploads))
    return database, uploads


def verified_backup(database, tmp_path):
    backup = tmp_path / 'backup'
    local_data.backup(backup); local_data.verify(backup)
    return backup


def test_clean_migration_and_schema_contract(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path}/clean.db')
    try:
        upgrade(engine); upgrade(engine)
        with engine.connect() as conn:
            assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
            assert conn.exec_driver_sql('PRAGMA foreign_key_check').all() == []
            assert conn.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == EXPECTED_DB_REVISION
            inspector = sa.inspect(conn)
            for name, table in metadata().tables.items():
                assert set(table.c.keys()) <= {c['name'] for c in inspector.get_columns(name)}
                assert {i.name for i in table.indexes} <= {i['name'] for i in inspector.get_indexes(name)}
                actual = {(tuple(f['constrained_columns']), f['referred_table'], f['options'].get('ondelete')) for f in inspector.get_foreign_keys(name)}
                assert {(tuple(e.parent.name for e in f.elements), f.elements[0].column.table.name, f.ondelete) for f in table.foreign_key_constraints} <= actual
    finally:
        engine.dispose()


def test_dry_run_and_verified_repair_no_content_loss(legacy, tmp_path, capsys):
    database, uploads = legacy
    before = local_data.digest(database)
    plan = read_plan(database)
    assert plan == read_plan(database) and before == local_data.digest(database)
    assert not plan['ambiguous'] and plan['legacy_quarantined'] == 187
    assert len(plan['actions']) == 5  # Two legacy ops, audit, session and link.
    assert 'private-token-hash' not in json.dumps(plan)
    backup = verified_backup(database, tmp_path)
    result = apply_repair(database, plan, backup)
    assert result['foreign_key_violations'] == 0 and result['legacy_quarantined'] == 187
    with sqlite3.connect(database) as conn:
        assert conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        assert conn.execute('SELECT count(*) FROM integrity_archive').fetchone()[0] == 5
        assert conn.execute('SELECT count(*) FROM sync_outbox WHERE protocol_version=1').fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM sync_outbox WHERE payload_json=' {\"historical\":true} ' AND status='pending' AND tries=9 AND client_id IS NULL AND remote_key IS NULL").fetchone()[0] == 187
        assert conn.execute('SELECT revision FROM notes WHERE id="n-a"').fetchone()[0] == 7
        assert conn.execute('SELECT count(*) FROM audit_logs').fetchone()[0] == 1
        assert json.loads(conn.execute("SELECT original_json FROM integrity_archive WHERE source_table='refresh_tokens'").fetchone()[0])['token_hash'] == 'private-token-hash'
    assert (uploads/'keep.md').read_text() == '# keep bytes'
    assert status(make_engine(f'sqlite:///{database}'), uploads, columns=True)['ok']
    # New schema backup/restore covers every table, migration head, FK and bytes.
    after = tmp_path/'after'; local_data.backup(after); local_data.verify(after)
    manifest = json.loads((after/'manifest.json').read_text())
    assert manifest['schema'] == {'revisions': [EXPECTED_DB_REVISION], 'foreignKeyViolations': 0}
    assert manifest['counts']['integrity_archive'] == 5
    assert 'private-token-hash' not in capsys.readouterr().out


@pytest.mark.parametrize('fault', ['stale', 'ambiguous', 'bad_backup', 'migration'])
def test_repair_rejects_unsafe_plans_and_rolls_back(legacy, tmp_path, monkeypatch, fault):
    database, _ = legacy
    if fault == 'ambiguous':
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE notes SET user_id=NULL WHERE id='n-a'")
    plan = read_plan(database)
    backup = verified_backup(database, tmp_path)
    if fault == 'bad_backup':
        (backup/'VERIFIED.json').write_text('{"manifestSHA256":"wrong"}')
    elif fault == 'stale':
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE notes SET title='new saved edit' WHERE id='n-a'")
    elif fault == 'migration':
        from app.db import migration_steps
        original = migration_steps.enforce_schema
        def fail(conn):
            original(conn)
            raise RuntimeError('injected failure after all DDL')
        monkeypatch.setattr(migration_steps, 'enforce_schema', fail)
    before = read_plan(database)
    with pytest.raises((ValueError, RuntimeError)):
        apply_repair(database, plan, backup)
    assert read_plan(database) == before


def test_dirty_db_upgrade_fails_atomically(legacy):
    database, _ = legacy
    before = read_plan(database)
    engine = make_engine(f'sqlite:///{database}')
    try:
        with pytest.raises(RuntimeError, match='Integrity repair required'):
            upgrade(engine)
        assert read_plan(database) == before
        with engine.connect() as conn:
            assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
    finally:
        engine.dispose()


def test_connection_enforcement_invalid_fk_and_cross_owner():
    with db.get_session() as session:
        for uid in ('a','b'):
            session.add(User(id=uid, username=uid, password_hash='unused'))
            session.add(Note(id='n-'+uid, user_id=uid, title='keep'))
    with pytest.raises(IntegrityError), db.get_session() as session:
        session.add(NoteTag(note_id='missing', tag='invalid'))
        session.flush()
    with pytest.raises(IntegrityError), db.get_session() as session:
        session.add(NoteLink(from_id='n-a', to_id='n-b'))
        session.flush()
    with db.engine.connect() as a, db.engine.connect() as b:
        if db.engine.dialect.name == 'sqlite':
            assert a.exec_driver_sql('PRAGMA foreign_keys').scalar() == b.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1


@pytest.mark.parametrize('loaded', [False, True])
def test_hard_delete_cascade_and_set_null(loaded, tmp_path):
    import datetime as dt
    file = tmp_path/'keep.md'; file.write_text('keep')
    with db.get_session() as s:
        s.add(User(id='u',username='u',password_hash='unused'))
        s.add(Note(id='n',user_id='u',title='keep'))
        s.add(FileAsset(id='f',note_id='n',user_id='u',kind='markdown',mime='text/markdown',filename='keep.md',size=4,path_original=str(file)))
        s.add(NoteTag(note_id='n',tag='keep'))
        s.add(RefreshToken(id='r',user_id='u',token_hash='unused',expires_at=dt.datetime.utcnow()))
        s.add(AuditLog(id='a',user_id='u',event='keep'))
        s.flush()
        s.add(SyncOutbox(id='o',user_id='u',note_id='n',op_type='legacy'))
        s.add(SyncConflict(id='c',local_note_id='n',user_id='u',payload_json='{"draft":"keep"}'))
    with db.get_session() as s:
        note = s.get(Note, 'n')
        if loaded: assert note.files and note.tags
        s.delete(note)
    with db.get_session() as s:
        assert s.get(FileAsset,'f').note_id is None
        assert s.get(SyncOutbox,'o').note_id is None
        assert s.get(SyncConflict,'c').local_note_id is None
        assert s.query(NoteTag).count() == 0
        user = s.get(User,'u')
        if loaded: assert user.files and user.refresh_tokens
        s.delete(user)
    with db.get_session() as s:
        assert s.get(FileAsset,'f') is None and s.get(RefreshToken,'r') is None
        assert s.get(AuditLog,'a').user_id is None
        assert s.get(SyncOutbox,'o').user_id is None
        assert s.get(SyncConflict,'c').payload_json == '{"draft":"keep"}'
    assert file.read_text() == 'keep'


def test_readyz_and_liveness_are_separate():
    with TestClient(app) as client:
        assert client.get('/healthz').status_code == client.get('/readyz').status_code == 200
        with db.engine.begin() as c:
            c.exec_driver_sql("UPDATE alembic_version SET version_num='wrong'")
        result = client.get('/readyz')
        assert result.status_code == 503 and result.json()['checks']['revision'] is False
        assert client.get('/healthz').status_code == 200
    with pytest.raises(RuntimeError, match='not ready'), TestClient(app):
        pass


def test_readiness_missing_table_storage_and_unreachable_db(tmp_path):
    assert not status(db.engine, tmp_path/'missing')['checks']['storage']
    with db.engine.begin() as c:
        c.exec_driver_sql('DROP TABLE sync_peer_state')
    assert not status(db.engine, tmp_path)['checks']['tables']
    class Broken:
        def connect(self): raise RuntimeError('password-never-expose')
    result = status(Broken(), tmp_path)
    assert not result['ok'] and 'password-never-expose' not in json.dumps(result)


def test_production_disallows_startup_ddl(monkeypatch):
    from app.core.config import Settings
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('DB_AUTO_MIGRATE','true')
    with pytest.raises(ValueError, match='explicit migrations'):
        Settings()


def test_migration_unknown_schema_and_restart_after_failure(tmp_path, monkeypatch):
    from app.db import migration_steps
    engine = make_engine(f'sqlite:///{tmp_path}/migration.db')
    try:
        original = migration_steps.enforce_schema
        def fail(conn):
            original(conn)
            raise RuntimeError('fault after constraints')
        with monkeypatch.context() as patch:
            patch.setattr(migration_steps, 'enforce_schema', fail)
            with pytest.raises(RuntimeError, match='fault after constraints'):
                upgrade(engine)
        with engine.connect() as c:
            assert sa.inspect(c).get_table_names() == []
            assert c.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
        upgrade(engine)
        with engine.connect() as c:
            assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == EXPECTED_DB_REVISION
        with engine.begin() as c:
            c.exec_driver_sql("UPDATE alembic_version SET version_num='future_unknown'")
        with pytest.raises(Exception, match='future_unknown'):
            upgrade(engine)
        with engine.connect() as c:
            assert c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == 'future_unknown'
    finally:
        engine.dispose()


def test_partial_indexes_and_historical_columns_survive(legacy, tmp_path):
    database, _ = legacy
    with sqlite3.connect(database) as c:
        c.execute('ALTER TABLE notes ADD COLUMN legacy_extra TEXT')
        c.execute("UPDATE notes SET legacy_extra='keep' WHERE id='n-a'")
        c.execute("CREATE UNIQUE INDEX old_partial ON notes(legacy_extra) WHERE legacy_extra IS NOT NULL")
    backup = verified_backup(database, tmp_path)
    apply_repair(database, read_plan(database), backup)
    with sqlite3.connect(database) as c:
        assert c.execute("SELECT legacy_extra FROM notes WHERE id='n-a'").fetchone()[0] == 'keep'
        assert 'WHERE legacy_extra IS NOT NULL' in c.execute("SELECT sql FROM sqlite_master WHERE name='old_partial'").fetchone()[0]


def test_startup_does_not_mutate_schema_by_default(monkeypatch):
    from app.db import migrate
    def unexpected(*args, **kwargs):
        raise AssertionError('Unrequested startup DDL')
    monkeypatch.setattr(migrate, 'upgrade', unexpected)
    with TestClient(app) as client:
        assert client.get('/readyz').status_code == 200


def test_missing_column_refuses_startup(tmp_path):
    engine = make_engine(f'sqlite:///{tmp_path}/missing-column.db')
    try:
        upgrade(engine)
        with engine.begin() as c:
            c.exec_driver_sql('ALTER TABLE sync_peer_state RENAME COLUMN last_error TO broken_column')
        assert not status(engine,tmp_path,columns=True)['checks']['columns']
    finally:
        engine.dispose()


def test_active_dialect_migration_failure_is_atomic(monkeypatch):
    from app.db import migration_steps
    schema = sa.MetaData(); schema.reflect(bind=db.engine); schema.drop_all(db.engine)
    original = migration_steps.enforce_schema
    def fail(conn):
        original(conn)
        raise RuntimeError('injected active dialect DDL failure')
    with monkeypatch.context() as patch:
        patch.setattr(migration_steps, 'enforce_schema', fail)
        with pytest.raises(RuntimeError, match='active dialect DDL failure'):
            upgrade(db.engine)
    with db.engine.connect() as c:
        assert sa.inspect(c).get_table_names() == []
    upgrade(db.engine)
    with TestClient(app) as client:
        assert client.get('/readyz').status_code == 200


def test_legacy_data_import_does_not_swallow_integrity_failure():
    from migrate_desktop_to_shared import _insert_row
    with sqlite3.connect(':memory:') as c:
        c.executescript('PRAGMA foreign_keys=ON; CREATE TABLE parent(id TEXT PRIMARY KEY); CREATE TABLE child(id TEXT PRIMARY KEY, parent_id TEXT REFERENCES parent(id));')
        with pytest.raises(sqlite3.IntegrityError):
            _insert_row(c, 'child', {'id':'new', 'parent_id':'absent'}, ['id','parent_id'])
        c.execute("INSERT INTO parent VALUES ('valid')")
        assert _insert_row(c, 'child', {'id':'new', 'parent_id':'valid'}, ['id','parent_id'])
        assert not _insert_row(c, 'child', {'id':'new', 'parent_id':'valid'}, ['id','parent_id'])
