"""Runtime failure/contended-path contracts. conftest isolates every DB and upload root."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import errno
import io
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event
from app.main import app
from app.core.config import settings, Settings
from app.db import session as db
from app.db.models import FileAsset, Note, NoteChunk
from app.services import files, runtime, upload_pipeline
from app.services.storage import atomic_write
from test_stabilization import users
from test_upload_api import make_wav


def upload(client, data=b'hello runtime', name='runtime.txt', **kwargs):
    return client.post('/api/upload?noteId=n-a', files={'files': (name, data, 'text/plain')}, **kwargs)


def test_three_users_slow_work_does_not_block_save_read_search(users, monkeypatch, tmp_path):
    from app.api import chat
    from app.agent import orchestrator
    from app.agent.draft_types import AgentReply
    from app.models.user import User
    from app.core.security import create_access_token
    with db.get_session() as session:
        session.add(User(id='c', username='third', password_hash='unused', is_active=True))
    shared = TestClient(app)
    class Actor:
        def __init__(self, headers): self.headers = headers
        def __getattr__(self, method):
            def request(path, **kwargs):
                headers = {**self.headers, **kwargs.pop('headers', {})}
                return getattr(shared, method)(path, headers=headers, **kwargs)
            return request
    a, b = (Actor(users[u]) for u in ('a','b'))
    c = Actor({'Authorization':f'Bearer {create_access_token("c")}'})
    media_path = tmp_path/'b.txt'; media_path.write_bytes(b'owned by b')
    with db.get_session() as session: session.get(FileAsset,'f-b').path_original=str(media_path)
    conversion_started, ai_started, release = (threading.Event() for _ in range(3))
    original = upload_pipeline.prepare_upload
    def slow_conversion(*args, **kwargs):
        assert db.engine.pool.checkedout() == 0
        conversion_started.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    class SlowLLM:
        def chat(self, *args):
            assert db.engine.pool.checkedout() == 0
            ai_started.set()
            assert release.wait(5)
            return '{"reply":"ready","draft":[]}'
    monkeypatch.setattr(upload_pipeline, 'prepare_upload', slow_conversion)
    monkeypatch.setattr(orchestrator, 'get_llm', lambda: SlowLLM())
    with shared, ThreadPoolExecutor(2) as executor:
        conversion = executor.submit(upload, a)
        assert conversion_started.wait(3)
        ai = executor.submit(c.post, '/api/chat', json={'text':'hello'})
        assert ai_started.wait(3)
        try:
            start = time.monotonic()
            detail = b.get('/api/notes/n-b')
            assert detail.status_code == 200
            assert b.get('/api/notes').status_code == 200
            assert b.patch('/api/notes/n-b', json={'title':'saved while busy'},
                           headers={'If-Match':str(detail.json()['revision'])}).status_code == 200
            assert b.get('/api/notes/search/full?q=saved').status_code == 200
            assert b.get('/files/f-b/original').content == b'owned by b'
            assert b.get('/healthz').status_code == 200
            assert b.get('/readyz').status_code == 200
            assert b.get('/api/notes/n-a').status_code == 404
            assert time.monotonic()-start < 2
        finally:
            release.set()
        assert conversion.result(timeout=10).status_code == 200
        assert ai.result(timeout=10).status_code == 200
    with db.get_session() as session: assert session.get(Note,'n-b').title == 'saved while busy'


def test_process_timeout_kills_process_group_and_bounds_output(tmp_path):
    marker = tmp_path/'late'
    child = f'import time;time.sleep(1);open({str(marker)!r},"w").write("leak")'
    parent = f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{child!r}]);time.sleep(20)'
    with pytest.raises(HTTPException) as error:
        runtime.run_tool([sys.executable, '-c', parent], timeout=.1)
    assert error.value.status_code == 504
    time.sleep(1.1)
    assert not marker.exists() and not runtime._processes
    result = runtime.run_tool([sys.executable,'-c','import sys;sys.stdout.write("x"*200000);sys.stderr.write("y"*200000)'])
    assert len(result.stdout) == len(result.stderr) == settings.subprocess_output_bytes
    with pytest.raises(HTTPException) as error:
        runtime.run_tool(['ovc-nonexistent-executable'])
    assert error.value.status_code == 503


def test_failed_conversion_and_commit_clean_new_assets(users, monkeypatch):
    a = TestClient(app, headers=users['a'])
    before = {str(p) for p in files.UPLOAD_ROOT.rglob('*') if p.is_file()}
    def fail(*args, **kwargs): raise HTTPException(504, 'Conversion timed out')
    with monkeypatch.context() as m:
        m.setattr(upload_pipeline, 'run_tool', fail)
        assert upload(a).status_code == 504
    import app.api.upload as api
    with monkeypatch.context() as m:
        m.setattr(api, 'record_file_change', lambda *a: (_ for _ in ()).throw(RuntimeError('injected commit failure')))
        assert upload(a).status_code == 500
    with db.get_session() as session:
        assert session.query(FileAsset).count() == 2
    assert before == {str(p) for p in files.UPLOAD_ROOT.rglob('*') if p.is_file()}


def test_upload_limits_invalid_archive_unsupported_retry(users, monkeypatch):
    a = TestClient(app, headers=users['a'])
    with monkeypatch.context() as m:
        m.setattr(settings, 'max_file_bytes', 4)
        assert upload(a, b'longer').status_code == 413
    assert a.post('/api/upload',files={'files':('file.unknown',b'bad','application/octet-stream')}).status_code == 415
    assert upload(a, b'not zip', name='file.docx').status_code == 422
    key = {'X-Upload-Op-Id':'stage6-retry'}
    first = upload(a, headers=key)
    assert first.status_code == 200, first.text
    assert upload(a, headers=key).json()['files'][0]['id'] == first.json()['files'][0]['id']
    assert upload(a, b'different bytes', headers=key).status_code == 409


def test_request_body_limits_chunked_and_declared(users, monkeypatch):
    monkeypatch.setattr(settings, 'max_request_bytes', 64)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver', headers=users['a']) as client:
            async def chunks():
                yield b'{"text":"'
                yield b'x'*128
                yield b'"}'
            response = await client.post('/api/chat', content=chunks(), headers={'Content-Type':'application/json'})
            assert response.status_code == 413, response.text
            response = await client.post('/api/chat', content=b'{}', headers={'Content-Length':'1000'})
            assert response.status_code == 413
            assert response.headers['x-content-type-options'] == 'nosniff'
    asyncio.run(check())


def test_low_storage_readiness_and_atomic_enospc(users, monkeypatch, tmp_path):
    import app.services.storage as storage
    monkeypatch.setattr(storage.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    a = TestClient(app, headers=users['a'])
    assert a.get('/healthz').status_code == 200
    ready = a.get('/readyz')
    assert ready.status_code == 503 and ready.json()['checks']['storage'] is False
    assert upload(a).status_code == 507
    monkeypatch.setattr(storage.shutil, 'disk_usage', lambda _: SimpleNamespace(free=10**12))
    def enospc(*args): raise OSError(errno.ENOSPC, 'private path')
    monkeypatch.setattr(storage.os, 'replace', enospc)
    with pytest.raises(HTTPException) as error:
        atomic_write(tmp_path/'never-final', b'bytes')
    assert error.value.status_code == 507
    assert list(tmp_path.iterdir()) == []


def media(users, tmp_path):
    data = make_wav(2)
    path = tmp_path/'audio.wav'; path.write_bytes(data)
    with db.get_session() as session:
        asset = session.get(FileAsset, 'f-a')
        asset.kind, asset.mime, asset.filename = 'audio', 'audio/wav', 'quote" résumé.wav'
        asset.path_original, asset.size = str(path), len(data)
    return TestClient(app, headers=users['a']), data


def test_range_head_streaming_and_permissions(users, tmp_path, monkeypatch):
    a, data = media(users, tmp_path)
    def forbidden(*args): raise AssertionError('whole file read')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    for suffix in ('original','stream'):
        path = '/files/f-a/'+suffix
        response = a.get(path, headers={'Range':'bytes=10-19'})
        assert response.status_code == 206 and response.content == data[10:20]
        assert response.headers['content-range'] == f'bytes 10-19/{len(data)}'
        assert response.headers['content-length'] == '10'
        assert response.headers['accept-ranges'] == 'bytes'
        assert 'microphone=(self)' in response.headers['permissions-policy']
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert a.get(path, headers={'Range':'bytes=-7'}).content == data[-7:]
        assert a.get(path, headers={'Range':'bytes=20-'}).content == data[20:]
        for invalid in ('bytes=garbage','bytes=999999999-','bytes=12-2','items=0-1','bytes=-0'):
            assert a.get(path, headers={'Range':invalid}).status_code == 416, invalid
        head = a.head(path, headers={'Range':'bytes=garbage'})
        assert head.status_code == 200 and not head.content
        assert head.headers['content-length'] == str(len(data))
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        monkeypatch.setattr(app, 'openapi_schema', None)
        schema=app.openapi()
    ids=[operation['operationId'] for path in schema['paths'].values() for operation in path.values() if isinstance(operation,dict) and 'operationId' in operation]
    assert len(ids)==len(set(ids))
    assert not any('Duplicate Operation' in str(w.message) for w in caught)
    disposition = a.get('/files/f-a/original').headers['content-disposition']
    assert 'attachment;' in disposition and "filename*=utf-8''" in disposition


def test_active_content_never_served_as_executable_html(users, tmp_path):
    path=tmp_path/'evil.html';path.write_text('<script>alert(1)</script>')
    with db.get_session() as session:
        asset=session.get(FileAsset,'f-a');asset.path_original=str(path);asset.mime='text/html';asset.kind='code'
        asset.path_doc_html=str(path)
    a=TestClient(app, headers=users['a'])
    r=a.get('/files/f-a/original')
    assert r.headers['content-type'].startswith('application/octet-stream')
    assert r.headers['content-disposition'].startswith('attachment')
    r=a.get('/files/f-a/doc.html')
    assert 'sandbox' in r.headers['content-security-policy'] and "default-src 'none'" in r.headers['content-security-policy']


def test_search_empty_and_restart_tombstones(users):
    from app.rag.tfidf_index import TFIDFIndex
    fresh=TFIDFIndex()
    assert fresh.search('anything') == []
    fresh.upsert('n-a',[('c','!!!')]);assert fresh.search('word') == []
    with db.get_session() as session:
        session.add(NoteChunk(id='ca',idx=0,embedding='[]',note_id='n-a',text='sailing laser racing'))
        session.add(NoteChunk(id='cb',idx=0,embedding='[]',note_id='n-b',text='sailing private secret'))
    fresh=TFIDFIndex(persistent=True)
    assert [r['note_id'] for r in fresh.search('sailing',allowed_note_ids={'n-a'})] == ['n-a']
    with db.get_session() as session: session.get(Note,'n-a').tombstone=True
    fresh=TFIDFIndex(persistent=True)
    assert fresh.search('sailing',allowed_note_ids={'n-a'}) == []


@pytest.mark.parametrize('error,status', [(TimeoutError('private'),504),(type('RateError',(Exception,),{'status_code':429})('private'),429),(ValueError('private'),502)])
def test_ai_failures_do_not_change_note(users,monkeypatch,error,status):
    from app.agent import orchestrator
    class LLM:
        def chat(self,*args):
            assert db.engine.pool.checkedout()==0
            raise error
        def stream_chat(self,*args,**kwargs):
            raise error
            yield
    monkeypatch.setattr(orchestrator,'get_llm',lambda:LLM())
    a=TestClient(app,headers=users['a'])
    before=a.get('/api/notes/n-a').json()
    result=a.post('/api/chat',json={'text':'hello','noteId':'n-a'})
    assert result.status_code==status and 'private' not in result.text
    result=a.post('/api/chat/stream',json={'text':'hello','noteId':'n-a'})
    assert f'"status": {status}' in result.text and 'private' not in result.text
    assert a.get('/api/notes/n-a').json()==before


def test_cancelled_job_releases_capacity_only_after_exit():
    stopped=threading.Event()
    def operation():
        try:
            while True:
                runtime.check_cancelled();time.sleep(.01)
        finally: stopped.set()
    async def check():
        task=asyncio.create_task(runtime.run_blocking(operation))
        await asyncio.sleep(.05);task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert await asyncio.to_thread(stopped.wait,1)
        assert await runtime.run_blocking(lambda:'available')=='available'
    asyncio.run(check())


def test_concurrent_revision_guard_preserves_one_save(users):
    a=TestClient(app,headers=users['a'])
    before=a.get('/api/notes/n-a').json()
    gate=threading.Barrier(2)
    def save(title):
        gate.wait()
        return a.patch('/api/notes/n-a',json={'title':title},headers={'If-Match':str(before['revision'])})
    with ThreadPoolExecutor(2) as executor:
        result=list(executor.map(save,['first','second']))
    assert sorted(r.status_code for r in result)==[200,409]
    assert a.get('/api/notes/n-a').json()['revision']==before['revision']+1


def test_sqlite_busy_is_retryable_and_no_partial_save(users):
    if db.engine.dialect.name!='sqlite': pytest.skip('SQLite-specific contention')
    db.engine.dispose()
    def short_timeout(conn, _): conn.execute('PRAGMA busy_timeout=30')
    event.listen(db.engine,'connect',short_timeout)
    holder=db.engine.raw_connection();holder.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(HTTPException) as error:
            with db.get_session(immediate=True) as session: session.get(Note,'n-a').title='never'
        assert error.value.status_code==503 and error.value.headers['Retry-After']=='1'
    finally:
        holder.rollback();holder.close();event.remove(db.engine,'connect',short_timeout);db.engine.dispose()
    with db.get_session() as session: assert session.get(Note,'n-a').title=='private-a'


@pytest.mark.parametrize('extra', [{'AUTH_MODE':'none'},{'COOKIE_SECURE':'false'},{'CORS_ORIGINS':'*'},{'ALLOWED_HOSTS':'*'},{'TRUSTED_PROXY_IPS':'*'},{'TRUSTED_PROXY_IPS':'0.0.0.0/0'},{'DB_AUTO_MIGRATE':'true'},{'ALLOW_DESKTOP_DEV_FALLBACK':'true'}])
def test_public_config_rejects_unsafe_values(monkeypatch,extra):
    for k,v in {'APP_ENV':'production','PUBLIC_MODE':'true','AUTH_MODE':'local','COOKIE_SECURE':'true','ALLOWED_HOSTS':'notes.example.org','PUBLIC_BASE_URL':'https://notes.example.org',**extra}.items():monkeypatch.setenv(k,v)
    monkeypatch.delenv('ALLOW_UNSAFE_PUBLIC_NO_AUTH',raising=False)
    with pytest.raises(ValueError):Settings()


def test_https_proxy_trust_and_cookies(users, monkeypatch):
    from app.core.http_runtime import RuntimeHTTPMiddleware
    from starlette.responses import JSONResponse
    async def inner(scope, receive, send):
        await JSONResponse({'scheme':scope['scheme'],'ip':scope['client'][0]})(scope,receive,send)
    monkeypatch.setattr(settings,'trusted_proxy_ips',['127.0.0.1'])
    async def check():
        for peer,expected in [('127.0.0.1',('https','203.0.113.20')),('198.51.100.2',('http','198.51.100.2'))]:
            transport=httpx.ASGITransport(app=RuntimeHTTPMiddleware(inner),client=(peer,999))
            async with httpx.AsyncClient(transport=transport,base_url='http://testserver') as client:
                r=await client.get('/',headers={'X-Forwarded-Proto':'https','X-Forwarded-For':'203.0.113.20'})
                assert tuple(r.json().values())==expected
    asyncio.run(check())
    monkeypatch.setattr(settings,'cookie_secure',True);monkeypatch.setattr(settings,'public_mode',True)
    a=TestClient(app,base_url='https://testserver')
    r=a.get('/')
    assert 'Secure' in r.headers['set-cookie'] and 'SameSite=lax' in r.headers['set-cookie']
    assert r.headers['strict-transport-security']=='max-age=31536000'
    r=a.options('/api/notes',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'PATCH'})
    assert r.status_code==400 and 'access-control-allow-origin' not in r.headers


@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','172.16.0.2','192.168.1.1','169.254.169.254','::1','fe80::1','fc00::1','::ffff:127.0.0.1'])
def test_ssrf_blocks_private_dns_answers(ip,monkeypatch):
    from app.services.public_url import public_addresses
    from app.services import public_url
    monkeypatch.setattr(public_url,'run_tool',lambda *a,**k:SimpleNamespace(stdout=json.dumps([ip])))
    with pytest.raises(HTTPException) as error:public_addresses('vm.tiktok.com')
    assert error.value.status_code==400


def test_ssrf_rejects_credentials_schemes_and_redirect_before_connect(monkeypatch):
    from app.services import public_url as url
    for value in ('file:///etc/passwd','http://vm.tiktok.com/a','https://me:password@vm.tiktok.com/','https://127.0.0.1/','https://vm.tiktok.com:80/'):
        with pytest.raises(HTTPException):url.validate_public_url(value,{'vm.tiktok.com'})
    targets=[]
    class Connection:
        def __init__(self,*a,**k):pass
        def request(self,*a,**k):pass
        def getresponse(self):return SimpleNamespace(status=302,getheader=lambda _: 'https://169.254.169.254/latest/meta-data/')
        def close(self):pass
    monkeypatch.setattr(url,'public_addresses',lambda *args:['8.8.8.8'])
    monkeypatch.setattr(socket,'create_connection',lambda target,**k: targets.append(target) or object())
    monkeypatch.setattr(url.ssl,'create_default_context',lambda:SimpleNamespace(wrap_socket=lambda raw,**k:raw))
    monkeypatch.setattr(url.http.client,'HTTPSConnection',Connection)
    with pytest.raises(HTTPException):url._resolve_public_redirect('https://vm.tiktok.com/a',{'vm.tiktok.com'})
    assert targets==[('8.8.8.8',443)]


def test_graceful_shutdown_reaps_job_and_readiness_stays_cheap(users, monkeypatch):
    running=threading.Event()
    def work():
        running.set();runtime.run_tool([sys.executable,'-c','import time;time.sleep(30)'])
    async def check():
        task=asyncio.create_task(runtime.run_blocking(work))
        assert await asyncio.to_thread(running.wait,1)
        await asyncio.sleep(.1)
        await asyncio.to_thread(runtime.stop_runtime)
        with pytest.raises(HTTPException):await task
        assert not runtime._processes and not runtime._jobs
        runtime.start_runtime()
    asyncio.run(check())
    def no_scan(*a,**k):raise AssertionError('Readiness must not scan file tree')
    monkeypatch.setattr(Path,'rglob',no_scan)
    a=TestClient(app,headers=users['a']);start=time.monotonic()
    assert a.get('/readyz').status_code==200
    assert time.monotonic()-start<1


def test_bounded_rate_limiter_does_not_grow_with_unique_clients():
    from app.services.rate_limit import RateLimiter
    limiter=RateLimiter(max_keys=2)
    assert limiter.allow('a',1,60)
    assert not limiter.allow('a',1,60)
    assert limiter.allow('b',1,60)
    assert not limiter.allow('c',1,60)
    assert len(limiter._hits)==2


def test_client_disconnect_and_capacity_are_explicit(monkeypatch):
    started=threading.Event();stopped=threading.Event()
    def slow():
        started.set()
        try:
            while True: runtime.check_cancelled();time.sleep(.01)
        finally:stopped.set()
    class Request:
        async def is_disconnected(self):return started.is_set()
    async def check():
        with pytest.raises(HTTPException) as error:await runtime.run_for_request(Request(),slow)
        assert error.value.status_code==499
        assert await asyncio.to_thread(stopped.wait,1)
        acquired=[]
        try:
            while runtime._slots.acquire(blocking=False):acquired.append(True)
            with pytest.raises(HTTPException) as error:await runtime.run_blocking(lambda:None)
            assert error.value.status_code==503 and error.value.headers['Retry-After']=='2'
        finally:
            for _ in acquired:runtime._slots.release()
    asyncio.run(check())


def test_provider_closes_transport_on_errors_and_stream_close():
    from app.providers.llm_provider import GroqLLM
    closed=[]
    def failed(**kwargs):raise TimeoutError('private token')
    provider=GroqLLM.__new__(GroqLLM)
    provider._model_name='test';provider.temperature=.1;provider.max_tokens=10;provider.timeout=1
    provider._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=failed)),close=lambda:closed.append(True))
    with pytest.raises(TimeoutError):provider.chat('system','user')
    with pytest.raises(TimeoutError):list(provider.stream_chat('system','user'))
    assert len(closed)==2
    def stream():
        try:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='chunk'))])
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='more'))])
        finally:closed.append('stream')
    provider._client.chat.completions.create=lambda **kwargs:stream()
    result=provider.stream_chat('system','user');assert next(result)=='chunk';result.close()
    assert closed[-2:]==['stream',True]


def test_dns_deadline_is_explicit(monkeypatch):
    from app.services import public_url
    from app.services.public_url import public_addresses
    def timeout(*args,**kwargs):
        assert 0 < kwargs['timeout'] <= settings.external_http_timeout_seconds
        raise HTTPException(504, 'DNS timed out')
    monkeypatch.setattr(public_url,'run_tool',timeout)
    with pytest.raises(HTTPException) as error:public_addresses('vm.tiktok.com')
    assert error.value.status_code==504


def test_valid_public_configuration_and_private_sql_parameters(monkeypatch):
    for k,v in {'APP_ENV':'production','AUTH_MODE':'local','COOKIE_SECURE':'true','PUBLIC_MODE':'true',
                'ALLOWED_HOSTS':'notes.example.org','PUBLIC_BASE_URL':'https://notes.example.org','CORS_ORIGINS':'https://notes.example.org'}.items():monkeypatch.setenv(k,v)
    valid=Settings()
    assert valid.cors_origins==['https://notes.example.org'] and valid.cookie_secure
    assert db.engine.hide_parameters


def test_sync_processing_failure_is_not_misreported_as_auth(pair,monkeypatch):
    from app.services import sync_engine as sync
    pair.create('normal')
    monkeypatch.setattr(sync,'_pull',lambda *a: (_ for _ in ()).throw(HTTPException(504,'private converter path')))
    result=pair.run()
    assert result['reason']=='sync_error'
    assert 'auth_required' not in str(result)
    assert 'private converter path' not in str(result)


from test_sync_engine import pair


def test_pdf_and_spreadsheet_viewers_use_bounded_processes(users):
    import fitz
    from openpyxl import Workbook
    a=TestClient(app,headers=users['a'])
    document=fitz.open();page=document.new_page();page.insert_text((40,40),'Stage 6 PDF')
    data=document.tobytes();document.close()
    response=a.post('/api/upload?noteId=n-a',files={'files':('doc.pdf',data,'application/pdf')})
    assert response.status_code==200,response.text
    fid=response.json()['files'][0]['id']
    preview=a.get(f'/files/{fid}/page/1?scale=1.5')
    assert preview.status_code==200 and preview.headers['content-type']=='image/webp'
    assert a.get(f'/files/{fid}/page/999').status_code==404
    book=Workbook();book.active.append(['heading','value']);book.active.append(['alpha',42])
    content=io.BytesIO();book.save(content);book.close()
    response=a.post('/api/upload?noteId=n-a',files={'files':('book.xlsx',content.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert response.status_code==200,response.text
    fid=response.json()['files'][0]['id']
    window=a.get(f'/files/{fid}/excel/sheet/Sheet.json')
    assert window.status_code==200 and 'alpha' in window.text
    csv=a.get(f'/files/{fid}/excel/sheet/Sheet.csv')
    assert csv.status_code==200 and 'alpha,42' in csv.text


def test_body_deadline_and_preview_limit(users,monkeypatch):
    monkeypatch.setattr(settings,'request_body_timeout_seconds',.05)
    async def check():
        async def body():
            yield b'{"text":"'
            await asyncio.sleep(.1)
            yield b'hello"}'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',headers=users['a']) as client:
            r=await client.post('/api/chat',content=body(),headers={'Content-Type':'application/json'})
            assert r.status_code==408,r.text
    asyncio.run(check())
    monkeypatch.setattr(settings,'request_body_timeout_seconds',30)
    monkeypatch.setattr(settings,'max_preview_bytes',1)
    a=TestClient(app,headers=users['a'])
    assert upload(a).status_code==413
    with db.get_session() as session:assert session.query(FileAsset).count()==2


@pytest.mark.parametrize('mime,kind',[('video/webm','video'),('video/webm;codecs=vp8','video'),('audio/webm','audio'),('audio/webm;codecs=opus','audio')])
def test_webm_mime_distinguishes_video_from_recorded_audio(mime,kind):
    from starlette.datastructures import UploadFile, Headers
    uploaded=UploadFile(io.BytesIO(b'test'),filename='record.webm',headers=Headers({'content-type':mime}))
    metadata=files._classify_file(uploaded)
    assert metadata.kind==kind and metadata.mime==mime.split(';')[0]


def test_unexpected_error_is_safe_and_has_security_headers(monkeypatch,caplog):
    from app.db import readiness
    secret='private-note-and-token-must-not-be-logged'
    def broken(*args,**kwargs):raise RuntimeError(secret)
    monkeypatch.setattr(readiness,'status',broken)
    response=TestClient(app,raise_server_exceptions=False).get('/readyz')
    assert response.status_code==500 and secret not in response.text and secret not in caplog.text
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['x-request-id']==response.json()['requestId']
    assert 'unhandled_request' in caplog.text and 'RuntimeError' in caplog.text
