import asyncio
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
import pytest

from app.main import app, _proxy_remote_file_if_needed
from app.core.config import settings, Settings
from app.core.security import create_access_token, hash_password, get_current_user_or_refresh
from app.core.auth_provider import AuthUser, get_current_user_from_provider
from app.db.session import get_session
from app.db.models import Note, FileAsset, NoteLink, UserGroupPreference, SyncOutbox
from app.models.user import User
from app.models.session import RefreshToken
from app.agent.context import get_note_context, get_linked_notes, get_related_notes
from app.agent.block_models import normalize_blocks
from app.services import sync_engine
from app.rag.tfidf_index import index


@pytest.fixture
def users():
    with get_session() as session:
        for uid in ('a', 'b'):
            session.add(User(id=uid, username=f'user-{uid}', email=f'{uid}@example.org',
                             password_hash=hash_password('Valid123!'), is_active=True))
            session.add(Note(id=f'n-{uid}', user_id=uid, title=f'private-{uid}', blocks_json='[]'))
            session.add(FileAsset(id=f'f-{uid}', user_id=uid, note_id=f'n-{uid}',
                                  kind='txt', mime='text/plain', filename='test.txt', size=4, path_original='/missing'))
    return {uid: {'Authorization': f'Bearer {create_access_token(uid)}'} for uid in ('a', 'b')}


@pytest.mark.parametrize('owner,other', [('a', 'b'), ('b', 'a')])
def test_two_user_isolation(users, owner, other):
    client = TestClient(app, headers=users[owner])
    assert client.get(f'/api/notes/n-{owner}').status_code == 200
    for method, url, payload in [
        ('get', f'/api/notes/n-{other}', None),
        ('patch', f'/api/notes/n-{other}', {'title': 'stolen'}),
        ('delete', f'/api/notes/n-{other}', None),
        ('get', f'/files/f-{other}/original', None),
        ('get', f'/api/export/docx/n-{other}', None),
    ]:
        response = client.request(method, url, **({'json': payload} if payload else {}))
        assert response.status_code == 404, (url, response.text)
    assert client.post('/api/commit', json={'draft': [{
        'type': 'add_link', 'fromId': f'n-{owner}', 'toId': f'n-{other}', 'reason': 'private',
    }]}).status_code == 404
    assert client.post(f'/api/upload?noteId=n-{other}', files={'files': ('test.txt', b'text', 'text/plain')}).status_code == 404
    from sqlalchemy.exc import IntegrityError
    from app.db.session import engine
    from app.db.migration_steps import install_owner_guards
    with pytest.raises(IntegrityError), get_session() as session:
        session.add(NoteLink(from_id=f'n-{owner}', to_id=f'n-{other}'))
        session.flush()
    # Simulate a PRE-migration historical link only in this disposable fixture,
    # retaining the earlier regression for ownership filtering of corrupt data.
    with engine.begin() as connection:
        if engine.dialect.name == 'sqlite':
            connection.exec_driver_sql('DROP TRIGGER owner_note_links_insert')
            connection.exec_driver_sql('DROP TRIGGER owner_note_links_update')
        else:
            connection.exec_driver_sql('DROP TRIGGER owner_note_links ON note_links')
    with get_session() as session:
        session.add(NoteLink(from_id=f'n-{owner}', to_id=f'n-{other}'))
        session.flush()
        assert get_note_context(f'n-{other}', owner, session) is None
        assert get_note_context(f'n-{owner}', owner, session).links == []
        assert get_linked_notes(f'n-{owner}', owner, session) == []
        assert get_linked_notes(f'n-{other}', owner, session) == []
        index.upsert(f'n-{other}', [('foreign', 'private secret')])
        assert get_related_notes('secret', owner, session) == []
    with engine.begin() as connection:
        install_owner_guards(connection)
    assert client.get(f'/api/notes/n-{owner}').json()['linksFrom'] == []
    assert [n['id'] for n in client.get('/api/graph').json()['nodes']] == [f'n-{owner}']
    assert client.get('/api/notes/search/full?q=private').json()['total'] == 1


def test_preferences_and_orphans_are_isolated(users):
    a, b = (TestClient(app, headers=users[u]) for u in ('a', 'b'))
    assert a.post('/api/graph/groups/default/label', json={'label': 'A only'}).status_code == 200
    assert b.get('/api/graph/groups').json()['groups'][0]['label'] != 'A only'
    assert b.post('/api/graph/groups/default/label', json={'label': 'B only'}).status_code == 200
    assert a.get('/api/graph/groups').json()['groups'][0]['label'] == 'A only'
    with get_session() as session:
        session.add(Note(id='orphan', title='orphan'))
    for mode in ('local', 'none'):
        settings.auth_mode = mode
        settings.desktop_mode = True
        assert a.patch('/api/notes/orphan', json={'title': 'claimed'}).status_code == 404
    with get_session() as session:
        assert session.get(Note, 'orphan').user_id is None
        assert session.query(UserGroupPreference).count() == 2


def test_same_owner_links_and_tags_work(users):
    c = TestClient(app, headers=users['a'])
    other = c.post('/api/notes', json={'title': 'same owner'}).json()['id']
    result = c.post('/api/commit', json={'draft': [
        {'type': 'add_tag', 'noteId': 'n-a', 'tag': 'hello'},
        {'type': 'add_link', 'fromId': 'n-a', 'toId': other, 'reason': 'manual'},
    ]})
    assert result.status_code == 200, result.text
    note = c.get('/api/notes/n-a').json()
    assert note['tags'] == ['hello'] and len(note['linksFrom']) == 1


def test_ai_legacy_commit_edit_roundtrip(users):
    c = TestClient(app, headers=users['a'])
    block = {'id': 'ai-block', 'type': 'paragraph', 'data': {'source': 'ai', 'parts': [{'text': 'AI text'}]}}
    assert c.post('/api/commit', json={'draft': [{'type': 'insert_block', 'noteId': 'n-a', 'block': block}]}).status_code == 200
    note = c.get('/api/notes/n-a').json()
    note['blocks'][0]['data']['parts'][0]['text'] = 'Human edit'
    note['blocks'].append({'id': 'legacy', 'type': 'doc', 'data': {'kind': 'doc', 'src': '/files/old/original'}})
    response = c.patch('/api/notes/n-a', json={'blocks': note['blocks']})
    assert response.status_code == 200, response.text
    saved = c.get('/api/notes/n-a').json()['blocks']
    assert saved[0]['data']['parts'][0]['text'] == 'Human edit'
    assert saved[0]['data']['source'] == 'ai' and saved[1]['data']['kind'] == 'doc'
    bad = {'type': 'update_block', 'noteId': 'n-a', 'id': 'ai-block', 'patch': {'data': {'unknown': 'must not disappear'}}}
    rejected = c.post('/api/commit', json={'draft': [bad]})
    assert rejected.status_code == 422
    assert rejected.json()['detail'] == 'Invalid block data; no changes saved'
    assert c.get('/api/notes/n-a').json()['blocks'] == saved


@pytest.mark.parametrize('secure', [False, True])
def test_guest_pages_issue_consistent_csrf_cookie(secure):
    settings.cookie_secure = secure
    for path in ['/']:
        c = TestClient(app, base_url='https://testserver' if secure else 'http://testserver')
        response = c.get(path)
        assert response.status_code == 200
        assert c.cookies.get('csrf_token')
        cookie = response.headers['set-cookie'].lower()
        assert ('; secure' in cookie) == secure
        assert 'samesite=lax' in cookie


def test_empty_vocabulary_is_saveable(users):
    c = TestClient(app, headers=users['a'])
    response = c.patch('/api/notes/n-a', json={'blocks': [{'type': 'paragraph', 'data': {'parts': [{'text': '!!!'}]}}]})
    assert response.status_code == 200
    assert index.search('words') == []


def test_stale_editor_version_cannot_overwrite(users):
    c = TestClient(app, headers=users['a'])
    original = c.get('/api/notes/n-a').json()
    assert c.patch('/api/notes/n-a', json={'title': 'from another tab'}).status_code == 200
    stale = c.patch('/api/notes/n-a', json={'title': 'stale'}, headers={'If-Match': original['updatedAt']})
    assert stale.status_code == 409
    assert c.get('/api/notes/n-a').json()['title'] == 'from another tab'


def test_damaged_stored_json_is_not_returned_as_empty(users):
    with get_session() as session:
        session.get(Note, 'n-a').blocks_json = '{broken'
    c = TestClient(app, headers=users['a'])
    assert c.get('/api/notes/n-a').status_code == 409
    with get_session() as session:
        assert session.get(Note, 'n-a').blocks_json == '{broken'


@pytest.mark.parametrize('linked', [None, 'different-subject'])
def test_supabase_email_never_proves_link(users, linked):
    with get_session() as session:
        session.get(User, 'a').supabase_id = linked
    with patch('app.core.auth_provider.get_auth_user', return_value=AuthUser(id='new-subject', email='a@example.org', provider='supabase')):
        with pytest.raises(HTTPException) as caught:
            get_current_user_from_provider(Request({'type': 'http', 'headers': []}))
        assert caught.value.status_code == 409
    with get_session() as session:
        assert session.get(User, 'a').supabase_id == linked


def test_supabase_correct_link(users):
    with get_session() as session:
        session.get(User, 'a').supabase_id = 'subject-a'
    with patch('app.core.auth_provider.get_auth_user', return_value=AuthUser(id='subject-a', email='a@example.org', provider='supabase')):
        assert get_current_user_from_provider(Request({'type': 'http', 'headers': []})).id == 'a'


def login(client):
    response = client.post('/auth/login', json={'identifier': 'user-a', 'password': 'Valid123!'})
    assert response.status_code == 200, response.text
    return client.cookies.get('csrf_token')


def test_rotation_reuse_logout(users):
    c = TestClient(app)
    csrf = login(c)
    old = c.cookies.get('refresh_token')
    assert c.post('/auth/refresh', headers={'X-CSRF-Token': csrf}).status_code == 200
    assert c.cookies.get('refresh_token') != old
    c.cookies.set('refresh_token', old, domain='testserver.local', path='/')
    assert c.post('/auth/refresh', headers={'X-CSRF-Token': c.cookies.get('csrf_token')}).status_code == 401
    with get_session() as session:
        assert all(t.revoked_at for t in session.query(RefreshToken).all())
    result = c.post('/auth/logout', headers={'X-CSRF-Token': c.cookies.get('csrf_token')})
    assert result.status_code == 204
    assert 'Max-Age=0' in result.headers['set-cookie']
    assert not c.cookies.get('refresh_token')


def test_concurrent_rotation(users):
    c = TestClient(app)
    csrf = login(c)
    cookie = f"refresh_token={c.cookies.get('refresh_token')}; csrf_token={csrf}"
    def rotate(_):
        return TestClient(app).post('/auth/refresh', headers={'Cookie': cookie, 'X-CSRF-Token': csrf}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(rotate, range(2))) == [200, 401]
    with get_session() as session:
        assert all(t.revoked_at for t in session.query(RefreshToken).all())


def test_lockout_persists_and_naive_datetime_works(users):
    c = TestClient(app)
    with patch('app.api.routes.auth._rate_limiter.allow', return_value=True):
        for _ in range(10):
            assert c.post('/auth/login', json={'identifier': 'user-a', 'password': 'wrong'}).status_code == 401
        with get_session() as session:
            user = session.get(User, 'a')
            assert user.failed_login_count == 10 and user.locked_until
        assert c.post('/auth/login', json={'identifier': 'user-a', 'password': 'Valid123!'}).status_code == 423


@pytest.mark.parametrize('mode', ['supabase', 'none'])
def test_disabled_local_auth(users, mode):
    settings.auth_mode = mode
    c = TestClient(app)
    assert c.post('/auth/login', json={'identifier': 'user-a', 'password': 'Valid123!'}).status_code == 403
    assert c.post('/auth/refresh').status_code == 403
    assert c.get('/auth/verify?token=invalid').status_code == 403


def test_cookie_csrf_and_mode_fallback(users):
    c = TestClient(app)
    c.cookies.set('ovc_access_token', create_access_token('a'))
    assert c.patch('/api/notes/n-a', json={'title': 'bad'}).status_code == 403
    c.cookies.set('csrf_token', 'test-csrf')
    assert c.patch('/api/notes/n-a', json={'title': 'good'}, headers={'X-CSRF-Token': 'test-csrf'}).status_code == 200
    assert c.patch('/api/notes/n-a', json={'title': 'bearer'}, headers=users['a']).status_code == 200
    c = TestClient(app)
    login(c)
    settings.auth_mode = 'supabase'
    assert c.get('/files/f-a/original').status_code == 401


def test_public_none_guard(monkeypatch):
    monkeypatch.setenv('PUBLIC_MODE', 'true')
    monkeypatch.setenv('AUTH_MODE', 'none')
    monkeypatch.setenv('ALLOW_UNSAFE_PUBLIC_NO_AUTH', 'false')
    with pytest.raises(ValueError, match='Public AUTH_MODE=none'):
        Settings()


@pytest.mark.parametrize('mode', ['local', 'both'])
def test_bad_authorization_never_uses_cookie_identity(users, mode):
    settings.auth_mode = mode
    c = TestClient(app)
    c.cookies.set('ovc_access_token', create_access_token('a'))
    for header in ['Basic invalid', 'Bearer broken-token']:
        assert c.patch('/api/notes/n-a', json={'title': 'bypassed'},
                       headers={'Authorization': header}).status_code == 401
    with get_session() as session:
        assert session.get(Note, 'n-a').title == 'private-a'


def test_proxy_does_not_retry_foreign_file(users):
    from starlette.responses import Response
    settings.desktop_mode = True
    settings.sync_remote_base_url = 'https://remote.example'
    settings.sync_bearer_token = 'global-other-user-token'
    request = Request({'type': 'http', 'method': 'GET', 'scheme': 'http', 'server': ('localhost', 8000),
                       'path': '/files/f-b/original', 'query_string': b'',
                       'headers': [(b'authorization', users['a']['Authorization'].encode())]})
    original = Response(status_code=404)
    with patch('app.main.httpx.AsyncClient') as remote:
        assert asyncio.run(_proxy_remote_file_if_needed(request, original)) is original
        remote.assert_not_called()


def test_sync_cannot_adopt_other_owner(users):
    from app.services.sync_protocol import SyncOperation, apply_note_operation, identity
    import uuid
    with get_session(immediate=True) as session:
        op = SyncOperation(op_id=str(uuid.uuid4()), protocol_version=1, user_id='a',
            client_id=str(uuid.uuid4()), remote_key=identity(session, 'server_id'), entity_type='note',
            entity_local_id='local', entity_remote_id='n-b', operation_type='update',
            base_revision=0, payload={'title': 'stolen'})
        with pytest.raises(HTTPException) as error:
            apply_note_operation(session, 'a', op)
        assert error.value.status_code == 404
        assert session.get(Note, 'n-b').title == 'private-b'
    settings.sync_mode = 'remote-sync'
    settings.sync_remote_base_url = 'https://remote.test'
    with patch('app.services.sync_engine._build_client') as client:
        result = sync_engine.trigger_sync_now(access_token=users['b']['Authorization'].split()[1], user_id='a')
        assert result['reason'] == 'auth_required'
        client.assert_not_called()
