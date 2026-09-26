import json
from pathlib import Path
import sqlite3
import sys

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import local_data
from audit_local_data import audit
from repair_orphan_ownership import repair
from app.db.session import get_session, engine
from app.db.models import Note, FileAsset
from app.models.user import User
from app.db.stabilization_schema import upgrade


def test_backup_verification_and_explicit_repair(tmp_path, monkeypatch):
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    source_file = uploads / 'original.txt'
    source_file.write_text('private fixture')
    with get_session() as session:
        session.add(User(id='owner', username='owner', password_hash='fixture', is_active=True))
        session.add(Note(id='orphan', title='preserve', user_id=None))
        session.add(FileAsset(id='file', filename='original.txt', kind='txt', mime='text/plain',
                              size=15, note_id='orphan', path_original=str(source_file), user_id=None))
    database = Path(engine.url.database)
    monkeypatch.setattr(local_data, 'current_paths', lambda: (database, uploads))
    before = local_data.digest(database)
    backup = tmp_path / 'backup'
    local_data.backup(backup)
    local_data.verify(backup)
    assert (backup / 'VERIFIED.json').exists()
    assert local_data.digest(database) == before
    assert source_file.read_text() == 'private fixture'
    report = audit(database)
    assert report['notes_without_valid_owner'] == ['orphan']
    assert local_data.digest(database) == before
    plan = {'user_id': 'owner', 'note_ids': ['orphan'], 'file_ids': ['file']}
    assert not repair(database, plan)['applied']
    assert local_data.digest(database) == before
    with pytest.raises(ValueError, match='requires --backup'):
        repair(database, plan, apply=True)
    assert repair(database, plan, apply=True, backup=backup)['applied']
    with get_session() as session:
        assert session.get(Note, 'orphan').user_id == 'owner'
        assert session.get(FileAsset, 'file').user_id == 'owner'
    with pytest.raises(ValueError, match='already owned'):
        repair(database, plan)


def test_backup_corruption_fails_loudly(tmp_path, monkeypatch):
    database = Path(engine.url.database)
    uploads = tmp_path / 'uploads'; uploads.mkdir()
    monkeypatch.setattr(local_data, 'current_paths', lambda: (database, uploads))
    backup = tmp_path / 'backup'
    local_data.backup(backup)
    local_data.verify(backup)
    assert (backup / 'VERIFIED.json').exists()
    with (backup / 'database.sqlite3').open('ab') as f:
        f.write(b'damaged')
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        local_data.verify(backup)
    assert not (backup / 'VERIFIED.json').exists()


def test_backup_manifest_cannot_escape_restore_directory(tmp_path, monkeypatch):
    database = Path(engine.url.database)
    uploads = tmp_path / 'uploads'; uploads.mkdir()
    monkeypatch.setattr(local_data, 'current_paths', lambda: (database, uploads))
    backup = tmp_path / 'backup'
    local_data.backup(backup)
    manifest_file = backup / 'manifest.json'
    manifest = json.loads(manifest_file.read_text())
    manifest['sha256']['../outside'] = 'invalid'
    manifest_file.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='Invalid backup-relative path'):
        local_data.verify(backup)
    assert not (backup / 'VERIFIED.json').exists()


def test_additive_schema_preserves_legacy_and_is_repeatable(tmp_path):
    legacy = create_engine(f'sqlite:///{tmp_path}/legacy.db')
    with legacy.begin() as conn:
        conn.execute(text('CREATE TABLE users (id TEXT PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE refresh_tokens (id TEXT PRIMARY KEY, user_id TEXT)'))
        conn.execute(text("INSERT INTO refresh_tokens VALUES ('session', 'owner')"))
        conn.execute(text('CREATE TABLE sync_applied_ops (op_id TEXT)'))
        conn.execute(text("INSERT INTO sync_applied_ops VALUES ('keep-me')"))
        upgrade(conn); upgrade(conn)
        assert conn.execute(text('SELECT id,auth_provider FROM refresh_tokens')).one() == ('session', 'local')
        assert conn.execute(text('SELECT op_id FROM sync_applied_ops')).scalar_one() == 'keep-me'
    legacy.dispose()
