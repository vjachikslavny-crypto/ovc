"""Two isolated databases, actual server API, fault-injecting in-process HTTP."""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import threading
import uuid

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.db.engine import make_engine
from app.db.migrate import upgrade as migrate_database
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.security import create_access_token
from app.db import session as db
from app.db.base import Base
from app.db.models import Note, NoteLink, NoteTag, FileAsset, SyncOutbox, SyncEntityMap, SyncPeerState, SyncConflict, SyncAppliedOp
from app.main import app
from app.models.user import User
from app.services import sync_engine as sync
from app.services import sync_protocol as protocol
from app.services import files as file_service


class Pair:
    def __init__(self, tmp_path, monkeypatch):
        self.engine = make_engine(f'sqlite:///{tmp_path}/client.db')
        migrate_database(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.open_transactions = 0
        self.requests = []
        self.fault = None
        self.after = None
        self.tokens = {u: create_access_token(u) for u in ('a', 'b')}
        self.http = TestClient(app)
        for factory in (self.local, db.get_session):
            with factory() as session:
                for uid in ('a', 'b'):
                    session.add(User(id=uid, username=uid, password_hash='unused', is_active=True))
        monkeypatch.setattr(sync, 'get_session', self.local)
        monkeypatch.setattr(sync, '_build_client', self.build_client)
        settings.sync_mode, settings.sync_enabled = 'remote-sync', True
        settings.sync_remote_base_url = 'https://remote-a.test'
        settings.sync_pull_enabled, settings.sync_batch_size = True, 100
        settings.sync_outbox_max = 1000

    @contextmanager
    def local(self, *, immediate=False):
        session = self.factory()
        self.open_transactions += 1
        try:
            if immediate:
                session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()
            self.open_transactions -= 1

    def build_client(self, *, access_token=None):
        return httpx.Client(base_url=settings.sync_remote_base_url + '/',
            headers={'Authorization': f'Bearer {access_token}'}, transport=httpx.MockTransport(self.transport))

    def transport(self, request):
        assert self.open_transactions == 0, 'HTTP inside a local transaction'
        self.requests.append((request.method, request.url.path, request.content))
        if self.fault:
            response = self.fault(request)
            if response is not None:
                return response
        response = self.server(request.method, request.url.raw_path.decode(), content=request.content, headers=request.headers)
        if self.after:
            self.after(request, response)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers, request=request)

    def server(self, method, url, uid='a', **kwargs):
        mode = settings.sync_mode
        settings.sync_mode = 'off'
        try:
            kwargs.setdefault('headers', {'Authorization': f'Bearer {self.tokens[uid]}'})
            return self.http.request(method, url, **kwargs)
        finally:
            settings.sync_mode = mode

    def create(self, title='Local', uid='a', nid=None):
        with self.local(immediate=True) as session:
            note = Note(id=nid or str(uuid.uuid4()), user_id=uid, title=title)
            session.add(note)
            protocol.record_note_change(session, note, 'create')
            sync.enqueue_sync_operation(session, sync.OP_CREATE_NOTE, {}, note_id=note.id, user_id=uid)
            return note.id

    def edit(self, nid, title=None, tags=None, links=None, blocks=None, delete=False, uid='a'):
        with self.local(immediate=True) as session:
            note = session.get(Note, nid)
            if title is not None: note.title = title
            if blocks is not None: note.blocks_json = protocol.dumps(blocks)
            if tags is not None:
                session.query(NoteTag).filter(NoteTag.note_id == nid).delete()
                session.add_all(NoteTag(note_id=nid, tag=t) for t in tags)
            if links is not None:
                session.query(NoteLink).filter(NoteLink.from_id == nid).delete()
                session.add_all(NoteLink(from_id=nid, to_id=target, reason='link') for target in links)
            if delete: note.tombstone = True
            protocol.record_note_change(session, note, 'delete' if delete else 'update')
            sync.enqueue_sync_operation(session, sync.OP_DELETE_NOTE if delete else sync.OP_UPDATE_NOTE, {}, note_id=nid, user_id=uid)

    def run(self, uid='a'):
        return sync.trigger_sync_now(access_token=self.tokens[uid], user_id=uid)

    def scope(self, uid='a'):
        with self.local() as session:
            return sync._scope(session, uid)

    def mapping(self, nid, uid='a', kind='note'):
        with self.local() as session:
            return sync._mapping(session, sync._scope(session, uid), kind, nid)

    def due(self):
        with self.local() as session:
            for row in session.query(SyncOutbox).filter(SyncOutbox.protocol_version == 1):
                row.next_retry_at = None

    def rows(self):
        with self.local() as session:
            return session.query(SyncOutbox).order_by(SyncOutbox.created_at).all()

    def upload(self, nid, data=b'# local attachment\n'):
        with self.local(immediate=True) as session:
            upload = UploadFile(file=io.BytesIO(data), filename='offline.md', headers=Headers({'content-type': 'text/markdown'}))
            stored = asyncio.run(file_service.save_upload(session, upload, nid, 'a'))
            protocol.record_file_change(session, stored.asset)
            sync.enqueue_sync_operation(session, sync.OP_UPLOAD_FILE, {'fileAssetId': stored.asset.id}, note_id=nid, user_id='a')
            return stored.asset.id, stored.block


@pytest.fixture
def pair(tmp_path, monkeypatch):
    p = Pair(tmp_path, monkeypatch)
    yield p
    p.http.close()
    p.engine.dispose()


def test_standard_create_update_pull_and_durable_cursor(pair):
    nid = pair.create()
    pair.edit(nid, title='Offline edited')
    result = pair.run()
    assert result['ok'] and result['pushed'] == 3, result
    mapping = pair.mapping(nid)
    assert mapping.remote_id != nid and mapping.remote_revision == 3
    detail = pair.server('GET', f'/api/notes/{mapping.remote_id}').json()
    assert detail['title'] == 'Offline edited'
    pair.server('PATCH', f'/api/notes/{mapping.remote_id}', json={'title': 'From web'}, headers={
        'Authorization': 'Bearer ' + pair.tokens['a'], 'If-Match': f'"r{detail["revision"]}"'})
    assert pair.run()['ok']
    with pair.local() as session:
        assert session.get(Note, nid).title == 'From web'
        cursor = session.get(SyncPeerState, pair.scope()).cursor
    pair.engine.dispose()  # Simulate process losing every pooled connection.
    assert pair.run()['pulled'] == 0
    with pair.local() as session:
        assert session.get(SyncPeerState, pair.scope()).cursor == cursor
    assert all(r.status == 'applied' for r in pair.rows())


def test_lost_create_response_frozen_op_survives_restart(pair):
    nid = pair.create()
    lost = []
    def fault(request, response):
        if request.url.path.endswith('/push') and not lost:
            lost.append(request.content)
            raise httpx.ReadTimeout('lost response with secret text not to persist')
    pair.after = fault
    result = pair.run()
    assert not result['ok']
    first = pair.rows()[0]
    assert first.status == 'retry' and first.wire_json
    assert 'secret' not in first.last_error
    assert (first.next_retry_at - protocol.now()).total_seconds() > 0
    with db.get_session() as session:
        assert session.query(Note).count() == 1
    pair.engine.dispose()
    pair.after = None
    pair.due()
    assert pair.run()['ok']
    assert pair.rows()[0].wire_json == first.wire_json
    assert pair.mapping(nid)
    with db.get_session() as session:
        assert session.query(Note).count() == 1
        assert session.query(SyncAppliedOp).count() == 2


def test_restart_mid_operation_lease_replays_committed_result(pair):
    pair.create()
    scope = pair.scope()
    with pair.build_client(access_token=pair.tokens['a']) as client:
        sync._bind(scope, client.get('api/sync/hello').json(), ('local-user', 'a'))
        claim = sync._claim(scope)
        response = client.post('api/sync/push', json={'operations': [claim['wire']]})
        assert response.json()['results'][0]['status'] == 'applied'
    assert pair.rows()[0].status == 'inflight'
    pair.engine.dispose()
    assert sync._claim(scope) is None  # Durable lease not yet expired.
    pair.due()
    assert pair.run()['ok']
    with db.get_session() as session:
        assert session.query(Note).count() == 1


@pytest.mark.parametrize('status', [503, 429, 401])
def test_operation_error_classification_and_reauthentication(pair, status):
    pair.create()
    pair.fault = lambda req: httpx.Response(status) if req.url.path.endswith('/push') else None
    result = pair.run()
    row = pair.rows()[0]
    assert not result['ok']
    assert row.status == ('auth_required' if status == 401 else 'retry')
    assert row.tries == 1
    requests_before = len([r for r in pair.requests if r[1].endswith('/push')])
    if status != 401:
        pair.run()
        assert len([r for r in pair.requests if r[1].endswith('/push')]) == requests_before
    else:
        assert sync.get_sync_status(user_id='a')['authRequired']
    pair.fault = None
    pair.due()
    assert pair.run()['ok']
    assert not sync.get_sync_status(user_id='a')['authRequired']


def test_remote_unavailable_does_not_consume_pending_queue(pair):
    pair.create()
    def offline(request):
        raise httpx.ConnectError('secret URL')
    pair.fault = offline
    assert not pair.run()['ok']
    assert [r.tries for r in pair.rows()] == [0, 0]
    assert sync.get_sync_status(user_id='a')['remoteReachable'] is False


def test_pull_interrupted_apply_rolls_back_cursor_and_note(pair, monkeypatch):
    remote = pair.server('POST', '/api/notes', json={'title': 'Remote'}).json()
    original = sync._apply_page
    def crash(scope, changes, downloads, cursor, next_cursor):
        broken = deepcopy(changes)
        broken.append({'sequence': next_cursor + 1, 'entity_type': 'unsupported', 'entity_id': 'x', 'payload': {}})
        return original(scope, broken, downloads, cursor, next_cursor)
    monkeypatch.setattr(sync, '_apply_page', crash)
    assert not pair.run()['ok']
    with pair.local() as session:
        assert session.query(Note).count() == 0
        assert session.get(SyncPeerState, pair.scope()).cursor == 0
    monkeypatch.setattr(sync, '_apply_page', original)
    assert pair.run()['ok']
    with pair.local() as session:
        assert session.query(Note).one().title == remote['title']
        assert session.get(SyncPeerState, pair.scope()).cursor > 0


def test_concurrent_offline_edit_preserves_both_and_sync_continues(pair):
    nid = pair.create('Base')
    assert pair.run()['ok']
    rid = pair.mapping(nid).remote_id
    pair.edit(nid, title='Offline A')
    pair.edit(nid, title='Newest offline A')
    response = pair.server('PATCH', f'/api/notes/{rid}', json={'title': 'Online B'})
    assert response.status_code == 200
    result = pair.run()
    assert result['ok'], result
    with pair.local() as session:
        titles = {n.title for n in session.query(Note)}
        assert session.get(Note, nid).title == 'Online B'
        assert 'Newest offline A (conflict copy)' in titles
        assert session.query(SyncConflict).count() >= 1
    with db.get_session() as session:
        assert session.get(Note, rid).title == 'Online B'
        assert session.query(Note).filter(Note.title == 'Offline A (conflict copy)').count() == 1
    assert any(row.status == 'conflict' for row in pair.rows())
    pair.edit(nid, title='Resolved')
    assert pair.run()['ok']
    assert pair.server('GET', f'/api/notes/{rid}').json()['title'] == 'Resolved'


def test_offline_delete_and_stale_update_cannot_resurrect(pair):
    nid = pair.create()
    assert pair.run()['ok']
    rid = pair.mapping(nid).remote_id
    pair.edit(nid, title='Offline old edit')
    assert pair.server('DELETE', f'/api/notes/{rid}').status_code == 200
    assert pair.run()['ok']
    with pair.local() as session:
        assert session.get(Note, nid).tombstone
        assert session.query(Note).filter(Note.title == 'Offline old edit (conflict copy)', Note.tombstone.is_(False)).count() >= 1
    assert pair.server('GET', f'/api/notes/{rid}').status_code == 404
    second = pair.create('Delete locally')
    assert pair.run()['ok']
    remote_second = pair.mapping(second).remote_id
    pair.edit(second, delete=True)
    assert pair.run()['ok']
    with db.get_session() as session:
        assert session.get(Note, remote_second).tombstone


def test_tags_links_create_remove_and_dependency_mapping(pair):
    a, b = pair.create('A'), pair.create('B')
    pair.edit(a, tags=['one', 'two'], links=[b])
    pair.edit(b, links=[a])
    assert pair.run()['ok']
    ra, rb = pair.mapping(a).remote_id, pair.mapping(b).remote_id
    note = pair.server('GET', f'/api/notes/{ra}').json()
    assert set(note['tags']) == {'one', 'two'} and note['linksFrom'][0]['toId'] == rb
    pair.edit(a, tags=[], links=[])
    assert pair.run()['ok']
    note = pair.server('GET', f'/api/notes/{ra}').json()
    assert note['tags'] == [] and note['linksFrom'] == []


def test_link_target_on_later_pull_page_stays_hidden_until_applied(pair):
    a = pair.server('POST', '/api/notes', json={'title': 'A'}).json()['id']
    b = pair.server('POST', '/api/notes', json={'title': 'B'}).json()['id']
    pair.server('POST', '/api/commit', json={'draft': [{'type': 'add_link', 'fromId': a, 'toId': b, 'reason': 'related'}]})
    settings.sync_batch_size = 1
    assert pair.run()['ok']
    with pair.local() as session:
        assert session.query(Note).filter(Note.tombstone.is_(False)).count() == 2
        link = session.query(NoteLink).one()
        assert session.get(Note, link.from_id).title == 'A'
        assert session.get(Note, link.to_id).title == 'B'


def test_file_upload_retry_mapping_and_viewer_urls(pair):
    nid = pair.create()
    fid, block = pair.upload(nid)
    pair.edit(nid, blocks=[block])
    lost = []
    def lose_upload(request, response):
        if request.url.path.endswith('/sync/files') and not lost:
            lost.append(1)
            raise httpx.ReadTimeout('lost upload acknowledgement')
    pair.after = lose_upload
    assert not pair.run()['ok']
    pair.after = None
    pair.due()
    assert pair.run()['ok']
    mapped = pair.mapping(fid, kind='file')
    assert mapped.local_id != mapped.remote_id
    assert mapped.sha256 == hashlib.sha256(b'# local attachment\n').hexdigest()
    remote_note = pair.server('GET', '/api/notes/' + pair.mapping(nid).remote_id).json()
    assert mapped.remote_id in json.dumps(remote_note['blocks'])
    with db.get_session() as session:
        assert session.query(FileAsset).count() == 1
    with pair.local() as session:
        assert fid in session.get(Note, nid).blocks_json
    pair.engine.dispose()
    assert pair.mapping(fid, kind='file').remote_id == mapped.remote_id
    assert pair.run()['ok']


def test_pull_remote_file_gets_distinct_local_id_and_local_viewer(pair):
    remote = pair.server('POST', '/api/notes', json={'title': 'Remote file'}).json()['id']
    uploaded = pair.server('POST', f'/api/upload?noteId={remote}', files={'files': ('a.md', b'# remote', 'text/markdown')})
    assert uploaded.status_code == 200, uploaded.text
    result = uploaded.json()
    pair.server('PATCH', f'/api/notes/{remote}', json={'blocks': result['blocks']})
    assert pair.run()['ok']
    with pair.local() as session:
        asset = session.query(FileAsset).one()
        note = session.query(Note).filter(Note.tombstone.is_(False)).one()
        assert asset.id != result['files'][0]['id']
        assert asset.id in note.blocks_json and Path(asset.path_original).read_bytes() == b'# remote'
        assert asset.note_id == note.id


def test_user_switch_legacy_quarantine_and_wrong_token(pair):
    a, b = pair.create('A', 'a'), pair.create('B', 'b')
    with pair.local() as session:
        session.add_all([SyncOutbox(id='old-a', user_id='a', note_id=a, op_type='update_note'),
            SyncOutbox(id='old-null', user_id=None, note_id=a, op_type='create_note')])
    assert pair.run('a')['ok']
    assert pair.mapping(a) and pair.mapping(b, 'b') is None
    assert pair.run('b')['ok']
    assert pair.mapping(b, 'b')
    assert sync.trigger_sync_now(access_token=pair.tokens['b'], user_id='a')['reason'] == 'auth_required'
    with pair.local() as session:
        assert session.get(SyncOutbox, 'old-a').status == 'pending'
        assert session.get(SyncOutbox, 'old-null').tries == 0
        assert session.query(SyncPeerState).count() == 2
    assert sync.get_sync_status(user_id='a')['quarantinedLegacy'] == 1
    sent = [json.loads(r[2])['operations'][0]['user_id'] for r in pair.requests if r[1].endswith('/push')]
    assert sent == ['a', 'a', 'b', 'b']


def test_remote_switch_has_separate_mapping_cursor_and_pending(pair):
    nid = pair.create()
    assert pair.run()['ok']
    first = pair.mapping(nid)
    pair.edit(nid, title='Pending for A')
    settings.sync_remote_base_url = 'https://remote-b.test'
    assert pair.mapping(nid) is None
    assert pair.run()['ok']  # Separate scope even for a test peer serving same identity.
    assert pair.mapping(nid) is None
    with pair.local() as session:
        peers = session.query(SyncPeerState).all()
        assert len(peers) == 2
        assert len({p.remote_key for p in peers}) == 2
    settings.sync_remote_base_url = 'https://remote-a.test'
    assert pair.mapping(nid).remote_id == first.remote_id
    assert pair.run()['ok']


def test_same_url_changed_server_identity_is_blocked(pair):
    nid = pair.create()
    assert pair.run()['ok']
    pair.edit(nid, title='Pending')
    before = len([r for r in pair.requests if r[1].endswith('/push')])
    pair.fault = lambda req: httpx.Response(200, json={'protocol_version': 1, 'server_id': str(uuid.uuid4()),
        'user_id': 'a', 'auth_context': 'local-user', 'auth_subject': 'a'}) if req.url.path.endswith('/hello') else None
    assert not pair.run()['ok']
    assert len([r for r in pair.requests if r[1].endswith('/push')]) == before
    assert 'Pinned' in sync.get_sync_status(user_id='a')['lastError']


def test_queue_overflow_rolls_back_edit_and_never_drops_prior_rows(pair):
    nid = pair.create('Before')
    settings.sync_outbox_max = 2
    with pytest.raises(HTTPException) as error:
        pair.edit(nid, title='Unsaved draft')
    assert error.value.status_code == 503
    with pair.local() as session:
        assert session.get(Note, nid).title == 'Before'
        assert session.query(SyncOutbox).count() == 2


def test_dependency_failure_keeps_children_without_attempts(pair):
    pair.create()
    pair.fault = lambda req: httpx.Response(422) if req.url.path.endswith('/push') else None
    assert not pair.run()['ok']
    rows = pair.rows()
    assert rows[0].status == 'failed_permanent'
    assert rows[1].status == 'pending' and rows[1].tries == 0
    assert 'prerequisite' in rows[1].last_error


def test_worker_reverifies_captured_owner_each_cycle(pair, monkeypatch):
    import app.core.security as security
    from starlette.requests import Request
    settings.sync_worker_enabled = True
    settings.sync_bearer_token = pair.tokens['a']
    monkeypatch.setattr(sync, '_worker_started', False)
    monkeypatch.setattr(sync, '_sync_thread', None)
    captured = []
    class Thread:
        def __init__(self, **kwargs): captured.append(kwargs['target'])
        def start(self): pass
    monkeypatch.setattr(sync.threading, 'Thread', Thread)
    sync.start_sync_worker_once()
    assert len(captured) == 1
    settings.sync_bearer_token = pair.tokens['b']
    calls = []
    monkeypatch.setattr(sync, 'trigger_sync_now', lambda **kwargs: calls.append(kwargs) or {'reason': 'auth_required'})
    captured[0]()
    assert calls == [{'access_token': pair.tokens['a'], 'user_id': 'a', 'background': True}]


def test_remote_key_normalization_and_secret_url_rejection():
    assert sync.remote_key('https://EXAMPLE.com:443/') == sync.remote_key('https://example.com')
    assert sync.remote_key('http://example.com') != sync.remote_key('https://example.com')
    with pytest.raises(ValueError): sync.remote_key('https://user:password@example.com')


def test_all_187_legacy_rows_remain_unchanged_with_null_owner(pair):
    nid = pair.create()
    with pair.local() as session:
        for number in range(187):
            session.add(SyncOutbox(id=f'legacy-{number}', user_id=None if number == 0 else 'a',
                note_id=nid, op_type='create_note', payload_json='{"historical":true}', tries=2))
    assert pair.run()['ok']
    with pair.local() as session:
        rows = session.query(SyncOutbox).filter(SyncOutbox.protocol_version == 0).all()
        assert len(rows) == 187
        assert all(r.status == 'pending' and r.tries == 2 and r.wire_json is None and r.payload_json == '{"historical":true}' for r in rows)
    assert len([r for r in pair.requests if r[1].endswith('/push')]) == 2


def test_offline_attachment_then_delete_preserves_operation_order(pair):
    nid = pair.create()
    fid, block = pair.upload(nid)
    pair.edit(nid, blocks=[block])
    pair.edit(nid, delete=True)
    result = pair.run()
    assert result['ok'], (result, [(r.status, r.last_error) for r in pair.rows()])
    assert all(r.status == 'applied' for r in pair.rows())
    with db.get_session() as session:
        assert session.get(Note, pair.mapping(nid).remote_id).tombstone
        assert session.query(FileAsset).count() == 1


def test_deleted_original_does_not_break_conflict_copy_attachment(pair):
    nid = pair.create()
    fid, block = pair.upload(nid)
    pair.edit(nid, blocks=[block])
    assert pair.run()['ok']
    rid = pair.mapping(nid).remote_id
    pair.edit(nid, title='Offline file edit')
    pair.server('DELETE', f'/api/notes/{rid}')
    result = pair.run()
    assert result['ok'], result
    from app.core.ownership import get_owned_file
    with pair.local() as session:
        copies = session.query(Note).filter(Note.title == 'Offline file edit (conflict copy)', Note.tombstone.is_(False)).all()
        assert copies
        for note in copies:
            ids = protocol.file_ids(json.loads(note.blocks_json))
            assert ids and fid not in ids
            assert all(get_owned_file(session, f, 'a').note_id == note.id for f in ids)


def test_uncertain_ack_does_not_advance_past_newer_remote_change(pair):
    nid = pair.create()
    assert pair.run()['ok']
    rid = pair.mapping(nid).remote_id
    pair.edit(nid, title='Sent but unacknowledged')
    lost = []
    def lose(request, response):
        if request.url.path.endswith('/push') and not lost:
            lost.append(1)
            raise httpx.ReadTimeout('lost')
    pair.after = lose
    assert not pair.run()['ok']
    pair.after = None
    pair.server('PATCH', f'/api/notes/{rid}', json={'title': 'A newer web edit'})
    before = sync.get_sync_status(user_id='a')['cursor']
    assert not pair.run()['ok']
    assert sync.get_sync_status(user_id='a')['cursor'] == before
    pair.due()
    assert pair.run()['ok']
    with pair.local() as session:
        assert session.get(Note, nid).title == 'A newer web edit'


def test_new_relation_to_unmapped_legacy_note_transfers_full_content(pair):
    nid = pair.create('New')
    with pair.local() as session:
        session.add(Note(id='existing-local', title='Existing', user_id='a', blocks_json=protocol.dumps([
            {'id': 'block', 'type': 'heading', 'data': {'text': 'Legacy content retained', 'level': 2}}])))
    pair.edit(nid, links=['existing-local'])
    assert pair.run()['ok']
    rid = pair.mapping('existing-local').remote_id
    assert 'Legacy content retained' in json.dumps(pair.server('GET', f'/api/notes/{rid}').json()['blocks'])


def test_two_independent_remote_servers_never_share_cursor_or_outbox(pair, tmp_path):
    nid = pair.create('On A')
    assert pair.run()['ok']
    scope_a = pair.scope()
    rid_a = pair.mapping(nid).remote_id
    pair.edit(nid, title='Pending A')
    remote_b = make_engine(f'sqlite:///{tmp_path}/remote-b.db', connect_args={'check_same_thread': False})
    migrate_database(remote_b)
    factory_b = sessionmaker(bind=remote_b, autoflush=False, expire_on_commit=False)
    with factory_b.begin() as session:
        session.add(User(id='a', username='a', password_hash='unused', is_active=True))
    settings.sync_remote_base_url = 'https://remote-b.test'
    nid_b = pair.create('On B')
    original_transport = pair.transport
    def on_b(request):
        previous = db.SessionLocal
        db.SessionLocal = factory_b
        try:
            return original_transport(request)
        finally:
            db.SessionLocal = previous
    pair.transport = on_b
    try:
        assert pair.run()['ok']
        with pair.local() as session:
            a, b = session.get(SyncPeerState, scope_a), session.get(SyncPeerState, pair.scope())
            assert a.server_id != b.server_id
            assert sync._mapping(session, pair.scope(), 'note', nid) is None
        with factory_b() as session:
            assert {n.title for n in session.query(Note)} == {'On B'}
        settings.sync_remote_base_url = 'https://remote-a.test'
        pair.transport = original_transport
        assert pair.run()['ok']
        assert pair.server('GET', f'/api/notes/{rid_a}').json()['title'] == 'Pending A'
        assert pair.mapping(nid_b) is None
    finally:
        remote_b.dispose()


def test_download_failure_keeps_cursor_and_retries_without_duplicate_asset(pair):
    rid = pair.server('POST', '/api/notes', json={'title': 'Remote attachment'}).json()['id']
    uploaded = pair.server('POST', f'/api/upload?noteId={rid}', files={'files': ('a.md', b'# valid', 'text/markdown')}).json()
    pair.server('PATCH', f'/api/notes/{rid}', json={'blocks': uploaded['blocks']})
    pair.fault = lambda req: httpx.Response(503) if req.url.path.endswith('/original') else None
    assert not pair.run()['ok']
    with pair.local() as session:
        assert session.query(FileAsset).count() == 0
        assert session.get(SyncPeerState, pair.scope()).cursor == 0
    pair.fault = None
    assert pair.run()['ok']
    assert pair.run()['ok']
    with pair.local() as session:
        assert session.query(FileAsset).count() == 1


def test_malformed_ack_retries_exact_same_operation(pair):
    pair.create()
    changed = []
    original_transport = pair.transport
    def transport(request):
        response = original_transport(request)
        if request.url.path.endswith('/push') and not changed:
            changed.append(True)
            return httpx.Response(200, json={'results': [{'op_id': 'wrong', 'status': 'applied'}]})
        return response
    pair.transport = transport
    assert not pair.run()['ok']
    old = pair.rows()[0]
    assert old.status == 'retry'
    pair.due()
    assert pair.run()['ok']
    assert pair.rows()[0].wire_json == old.wire_json
    with db.get_session() as session:
        assert session.query(Note).count() == 1


@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'missing_row'])
def test_pull_repairs_mapped_file_without_changing_existing_local_urls(pair, damage):
    rid = pair.server('POST', '/api/notes', json={'title': 'Attachment'}).json()['id']
    uploaded = pair.server('POST', f'/api/upload?noteId={rid}', files={'files': ('a.md', b'# original', 'text/markdown')}).json()
    pair.server('PATCH', f'/api/notes/{rid}', json={'blocks': uploaded['blocks']})
    assert pair.run()['ok']
    with pair.local() as session:
        asset = session.query(FileAsset).one()
        fid, path = asset.id, Path(asset.path_original)
        if damage == 'missing_row':
            session.delete(asset)
    if damage == 'missing': path.unlink()
    if damage == 'corrupt': path.write_bytes(b'corrupt')
    pair.server('PATCH', f'/api/notes/{rid}', json={'title': 'Next event'})
    assert pair.run()['ok']
    with pair.local() as session:
        asset = session.query(FileAsset).one()
        assert asset.id == fid and Path(asset.path_original).read_bytes() == b'# original'
        assert fid in session.query(Note).filter(Note.tombstone.is_(False)).one().blocks_json


def test_account_switch_pauses_previous_users_background_worker_even_after_restart(pair):
    a, b = pair.create('A', 'a'), pair.create('B', 'b')
    assert pair.run('a')['ok']
    pair.edit(a, title='A pending after switch')
    assert pair.run('b')['ok']
    pair.engine.dispose()
    before = len(pair.requests)
    assert sync.trigger_sync_now(access_token=pair.tokens['a'], user_id='a', background=True) == {'ok': False, 'reason': 'account_switched'}
    assert len(pair.requests) == before
    with pair.local() as session:
        assert session.query(SyncOutbox).filter(SyncOutbox.user_id == 'a', SyncOutbox.status == 'pending').count() == 1
    assert pair.run('a')['ok']  # Explicitly selecting A resumes only A's queue.


def test_upload_to_unmapped_existing_note_preserves_its_full_content(pair):
    with pair.local() as session:
        session.add(Note(id='old-local', title='Existing note', user_id='a', blocks_json=protocol.dumps([
            {'id': 'original', 'type': 'heading', 'data': {'text': 'Never replace with identity shell', 'level': 2}}])))
    pair.upload('old-local')
    assert pair.run()['ok']
    rid = pair.mapping('old-local').remote_id
    assert 'Never replace' in json.dumps(pair.server('GET', f'/api/notes/{rid}').json()['blocks'])
    with pair.local() as session:
        assert 'Never replace' in session.get(Note, 'old-local').blocks_json
