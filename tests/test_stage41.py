"""Cross-subsystem regressions from the independent stages 0–4 audit.

Use the existing isolated two-database transport and authenticated CRUD fixtures.
"""
import json

import pytest
from fastapi.testclient import TestClient

from test_sync_engine import pair
from test_sync_protocol import server
from test_stabilization import users
from app.agent.block_models import normalize_blocks
from app.main import app
from app.db import session as db
from app.db.models import Note, FileAsset, NoteLink, SyncConflict, SyncOutbox
from app.services import sync_engine as sync
from app.services import sync_protocol as protocol


def test_editor_etag_survives_sync_conflict(pair, monkeypatch):
    nid = pair.create('Original')
    assert pair.run()['ok']
    rid = pair.mapping(nid).remote_id
    pair.edit(nid, title='Saved offline; editor remains open')
    with pair.local() as session:
        stale_revision = session.get(Note, nid).revision
        stale_timestamp = session.get(Note, nid).updated_at.isoformat()
    remote = pair.server('PATCH', f'/api/notes/{rid}', json={'title': 'New remote content'})
    assert remote.status_code == 200
    assert remote.json()['revision'] == stale_revision  # Same number, different contents.
    assert pair.run()['ok']
    with pair.local() as session:
        note = session.get(Note, nid)
        assert note.title == 'New remote content'
        assert note.revision > stale_revision
        assert note.updated_at.isoformat() > stale_timestamp
    assert pair.mapping(nid).remote_revision == remote.json()['revision']
    from app.api import notes, commit
    with monkeypatch.context() as patch:
        patch.setattr(notes, 'get_session', pair.local)
        patch.setattr(commit, 'get_session', pair.local)
        for etag in (f'r{stale_revision}', stale_timestamp):
            stale = pair.http.patch(f'/api/notes/{nid}', headers={
                'Authorization': f'Bearer {pair.tokens["a"]}', 'If-Match': f'"{etag}"',
            }, json={'title': 'Stale editor overwrites remote'})
            assert stale.status_code == 409
        stale_ai = pair.http.post('/api/commit', headers={'Authorization': f'Bearer {pair.tokens["a"]}'},
            json={'baseRevisions': {nid: stale_revision}, 'draft': [
                {'type': 'add_tag', 'noteId': nid, 'tag': 'Stale AI change'},
            ]})
        assert stale_ai.status_code == 409
    assert pair.run()['ok']
    final = pair.server('GET', f'/api/notes/{rid}').json()
    assert (final['title'], final['revision']) == ('New remote content', remote.json()['revision'])
    with pair.local() as session:
        assert session.query(Note).filter(Note.title == 'Saved offline; editor remains open (conflict copy)').count() >= 1


@pytest.mark.parametrize('delete_before_copy', [False, True])
def test_editor_recovery_copy_keeps_attachment_after_original_delete(users, delete_before_copy):
    with TestClient(app, headers=users['a']) as client:
        original = client.post('/api/notes', json={'title': 'Original'}).json()['id']
        uploaded = client.post(f'/api/upload?noteId={original}', files={
            'files': ('attachment.md', b'# file content', 'text/markdown'),
        })
        assert uploaded.status_code == 200
        blocks = uploaded.json()['blocks']
        fid = next(iter(protocol.file_ids(blocks)))
        if delete_before_copy:
            assert client.delete(f'/api/notes/{original}').status_code == 200
        recovered = client.post(f'/api/notes/{original}/recovery-copy', json={
            'title': 'Original', 'blocks': blocks, 'passport': {'summary': 'Draft metadata'},
        })
        assert recovered.status_code == 201, recovered.text
        copy = recovered.json()
        copied_fid = next(iter(protocol.file_ids(copy['blocks'])))
        assert copy['id'] != original and copied_fid != fid
        assert copy['passport'] == {'summary': 'Draft metadata'}
        assert client.get(f'/files/{copied_fid}/original').content == b'# file content'
        if not delete_before_copy:
            assert client.delete(f'/api/notes/{original}').status_code == 200
        assert client.get(f'/files/{fid}/original').status_code == 404
        assert client.get(f'/files/{copied_fid}/original').status_code == 200
        assert client.get(f'/files/{copied_fid}/original').content == b'# file content'
        with db.get_session() as session:
            copied = session.get(FileAsset, copied_fid)
            assert copied.note_id == copy['id'] and copied.user_id == 'a'
            assert copied.path_original == session.get(FileAsset, fid).path_original
        with TestClient(app, headers=users['b']) as other:
            assert other.get(f'/files/{copied_fid}/original').status_code == 404
            assert other.post(f'/api/notes/{original}/recovery-copy', json={
                'title': 'Stolen', 'blocks': blocks,
            }).status_code == 404
            assert other.post('/api/notes/n-b/recovery-copy', json={
                'title': 'Stolen files', 'blocks': blocks,
            }).status_code == 404


def test_delete_link_target_does_not_wedge_pending_update(pair):
    a, b = pair.create('A'), pair.create('B')
    pair.edit(a, links=[b])
    assert pair.run()['ok']
    ra, rb = pair.mapping(a).remote_id, pair.mapping(b).remote_id
    blocks = [{'id': 'text', 'type': 'paragraph', 'data': {'parts': [{'text': 'Offline body'}]}}]
    pair.edit(a, title='Offline A edit', blocks=blocks)
    assert pair.server('DELETE', f'/api/notes/{rb}').status_code == 200
    result = pair.run()
    remote = pair.server('GET', f'/api/notes/{ra}').json()
    assert remote['title'] == 'Offline A edit'
    assert remote['blocks'] == normalize_blocks(blocks) and remote['linksFrom'] == []
    assert result['ok'] and result['failed'] == 0
    assert all(row.status == 'applied' for row in pair.rows())
    with db.get_session() as session:
        assert session.get(Note, rb).tombstone
        assert session.query(NoteLink).filter_by(from_id=ra, to_id=rb).count() == 0
        conflict = session.query(SyncConflict).filter_by(kind='relation_target_deleted').one()
        assert json.loads(conflict.payload_json)['relation']['toId'] == rb
        assert conflict.user_id == 'a'
    with pair.local() as session:
        conflict = session.query(SyncConflict).filter_by(kind='relation_target_deleted').one()
        assert conflict.local_note_id == a and conflict.user_id == 'a'
        row = session.get(SyncOutbox, conflict.op_id)
        wire, receipt = json.loads(row.wire_json), json.loads(row.result_json)
        assert receipt['relation_conflicts'][0]['relation']['toId'] == rb
    assert sync.get_sync_status(user_id='a')['relationConflicts'] == 1
    assert sync.get_sync_status(user_id='b')['relationConflicts'] == 0
    assert pair.server('POST', '/api/sync/push', json={'operations': [wire]}).json()['results'] == [receipt]
    assert pair.run()['ok']
    with db.get_session() as session:
        assert session.query(SyncConflict).filter_by(kind='relation_target_deleted').count() == 1
    pair.edit(a, title='Next edit also syncs')
    assert pair.run()['ok']
    assert pair.server('GET', f'/api/notes/{ra}').json()['title'] == 'Next edit also syncs'


def test_preflight_failure_not_reported_as_success(pair):
    nid = pair.create()
    with pair.local() as session:
        session.get(Note, nid).user_id = 'b'
    for _ in range(2):
        result = pair.run()
        status = sync.get_sync_status(user_id='a')
        assert not result['ok']
        assert result['failed'] == status['failed'] == 1
        assert result['pending'] == status['pending'] == 1
        assert result['lastError'] == status['lastError'] == 'Local note ownership mismatch'
    assert any(row.status == 'failed_permanent' for row in pair.rows())
    assert not any(path.endswith('/push') for _, path, _ in pair.requests)
    response = pair.http.get('/api/sync/status', headers={'Authorization': f'Bearer {pair.tokens["a"]}'})
    assert response.json()['failed'] == 1
    trigger = pair.http.post('/api/sync/trigger', headers={'Authorization': f'Bearer {pair.tokens["a"]}'})
    assert trigger.json()['ok'] is False and trigger.json()['failed'] == 1


def test_ack_updates_remote_mapping_without_reusing_local_revision(pair):
    nid = pair.create()
    assert pair.run()['ok']
    pair.edit(nid, title='Local conflicting edit')
    assert pair.server('PATCH', f'/api/notes/{pair.mapping(nid).remote_id}',
                       json={'title': 'Remote winner'}).status_code == 200
    assert pair.run()['ok']  # Pull has advanced the local version beyond remote.
    pair.edit(nid, title='Unsent first edit')
    pair.edit(nid, title='Unsent second edit')
    scope = pair.scope()
    with pair.local() as session:
        before = (session.get(Note, nid).revision, session.get(Note, nid).updated_at)
    for _ in range(2):
        claim = sync._claim(scope)
        receipt = pair.server('POST', '/api/sync/push', json={'operations': [claim['wire']]}).json()['results'][0]
        sync._ack(scope, claim, receipt)
        assert pair.mapping(nid).remote_revision == receipt['revision']
        with pair.local() as session:
            note = session.get(Note, nid)
            assert (note.revision, note.updated_at) == before
            assert note.title == 'Unsent second edit'
    assert pair.run()['ok']
    with pair.local() as session:
        assert (session.get(Note, nid).revision, session.get(Note, nid).updated_at) == before
    pair.edit(nid, title='New edit uses mapped remote base')
    assert pair.run()['ok']
    assert pair.server('GET', f'/api/notes/{pair.mapping(nid).remote_id}').json()['title'] == 'New edit uses mapped remote base'


def test_own_sync_echo_does_not_invalidate_editor_or_legacy_timestamp(pair, monkeypatch):
    nid = pair.create()
    assert pair.run()['ok']
    pair.edit(nid, title='Current editor contents')
    with pair.local() as session:
        version = session.get(Note, nid).revision
        timestamp = session.get(Note, nid).updated_at
    assert pair.run()['ok']
    with pair.local() as session:
        note = session.get(Note, nid)
        assert note.revision == version and note.updated_at == timestamp
        protocol.check_revision(note, timestamp.isoformat())
    from app.api import notes
    monkeypatch.setattr(notes, 'get_session', pair.local)
    response = pair.http.patch(f'/api/notes/{nid}', headers={
        'Authorization': f'Bearer {pair.tokens["a"]}', 'If-Match': f'"r{version}"',
    }, json={'title': 'Still editing'})
    assert response.status_code == 200


@pytest.mark.parametrize('target_state', ['missing', 'foreign', 'foreign_deleted'])
def test_sync_does_not_relax_ownership_for_invalid_links(server, target_state):
    original = server.apply(server.operation(title='Original'))
    with db.get_session() as session:
        if target_state != 'missing':
            session.add(Note(id='target', user_id='bob', title='Private', tombstone=target_state == 'foreign_deleted'))
    op = server.operation(operation_type='update', entity_remote_id=original['entity_remote_id'],
        base_revision=original['revision'], payload={'title': 'Must roll back',
            'linksFrom': [{'toId': 'target', 'reason': 'Attempted relation'}]})
    result = server.push(op)[0]
    assert result['status'] == 'failed_permanent' and result['http_status'] == 404
    with db.get_session() as session:
        note = session.get(Note, original['entity_remote_id'])
        assert note.title == 'Original' and note.revision == original['revision']
        assert session.query(SyncConflict).count() == 0


def test_live_crud_still_rejects_new_links_to_deleted_targets(users):
    with TestClient(app, headers=users['a']) as client:
        target = client.post('/api/notes', json={'title': 'Target'}).json()['id']
        assert client.delete(f'/api/notes/{target}').status_code == 200
        result = client.post('/api/commit', json={'draft': [{
            'type': 'add_link', 'fromId': 'n-a', 'toId': target, 'reason': 'Stale manual selection',
        }]})
        assert result.status_code == 404
        assert client.get('/api/notes/n-a').json()['linksFrom'] == []


def test_desktop_recovery_copy_syncs_its_own_files_after_original_delete(pair, monkeypatch):
    nid = pair.create('Original')
    fid, block = pair.upload(nid)
    pair.edit(nid, blocks=[block])
    assert pair.run()['ok']
    original_remote = pair.mapping(nid).remote_id
    pair.edit(nid, delete=True)
    from app.api import notes
    with monkeypatch.context() as patch:
        patch.setattr(notes, 'get_session', pair.local)
        response = pair.http.post(f'/api/notes/{nid}/recovery-copy',
            headers={'Authorization': f'Bearer {pair.tokens["a"]}'},
            json={'title': 'Recovered offline', 'blocks': [block]})
    assert response.status_code == 201, response.text
    copy = response.json()
    assert fid not in protocol.file_ids(copy['blocks'])
    assert pair.run()['ok']
    remote_copy = pair.server('GET', f'/api/notes/{pair.mapping(copy["id"]).remote_id}').json()
    remote_fid = next(iter(protocol.file_ids(remote_copy['blocks'])))
    assert pair.server('GET', f'/api/notes/{original_remote}').status_code == 404
    assert pair.server('GET', f'/files/{remote_fid}/original').content == b'# local attachment\n'
    with db.get_session() as session:
        assert session.get(FileAsset, remote_fid).note_id == remote_copy['id']
