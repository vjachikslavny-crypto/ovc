import os, sys, tempfile, subprocess, time, json, socket, urllib.request, re
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='ovc-browser-') as tmp:
 os.environ.update(DATABASE_URL=f'sqlite:///{tmp}/browser.db', OVC_UPLOAD_ROOT=f'{tmp}/uploads', AUTH_MODE='local', APP_ENV='test', DESKTOP_MODE='false', SYNC_MODE='off', SYNC_ENABLED='false', SYNC_REMOTE_BASE_URL='', SYNC_BEARER_TOKEN='', PUBLIC_MODE='false', PUBLIC_BASE_URL='', COOKIE_SECURE='false', COOKIE_SAMESITE='lax', GROQ_API_KEY='', SECRET_KEY='browser-isolated-secret-no-real-data-ever', PYTHONDONTWRITEBYTECODE='1')
 sys.path.insert(0,str(root/'src'))
 from app.main import app
 from app.db.base import Base
 from app.db.session import engine,get_session
 from app.db.models import Note
 from app.models.user import User
 from app.core.security import hash_password
 from app.db.migrate import upgrade
 upgrade(engine)
 with get_session() as s:
  s.add(User(id='browser-user',username='browser-user',password_hash=hash_password('Browser123!'),is_active=True))
  s.add(Note(id='browser-note', user_id='browser-user', title='Browser note', blocks_json=json.dumps([{'id':'p1','type':'paragraph','data':{'parts':[{'text':'Initial text'}]}}])))
  s.add(Note(id='related-note', user_id='browser-user', title='Related note', blocks_json='[]'))
 with socket.socket() as sock:
  sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
 base=f'http://127.0.0.1:{port}'
 with open('/tmp/ovc-browser-server.log','w') as log:
  proc=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.main:app','--app-dir','src','--host','127.0.0.1','--port',str(port)],cwd=root,env=os.environ,stdout=log,stderr=log)
  try:
   for _ in range(100):
    try:
     urllib.request.urlopen(base+'/healthz',timeout=.3);break
    except Exception: time.sleep(.1)
   else: raise RuntimeError('isolated server did not start')
   with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    context=browser.new_context(base_url=base)
    context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())
    response=context.request.post('/auth/login',data={'identifier':'browser-user','password':'Browser123!'})
    assert response.status==200,response.text()
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    page.goto('/notes/browser-note')
    page.locator(".editor-save-status").wait_for(); page.locator(".editor:not([inert])").wait_for(state="attached")
    assert 'Initial text' in page.locator('#note-blocks').inner_text(), (page.locator('#note-blocks').inner_text(), errors)
    editable=page.locator('#note-blocks [contenteditable="true"]').first
    editable.fill('Saved normally')
    page.locator(".editor-save-status:disabled").wait_for()
    page.reload(); page.locator(".editor-save-status").wait_for(); page.locator(".editor:not([inert])").wait_for(state="attached")
    assert 'Saved normally' in page.locator('#note-blocks').inner_text()
    print('PASS normal save/reload',flush=True)
    # Immediate navigation must wait for the debounced payload to be acknowledged.
    page.locator('#note-blocks [contenteditable="true"]').first.fill('Immediate navigation')
    page.locator('#nav-back').click(); page.wait_for_url('**/notes')
    page.goto('/notes/browser-note');page.locator(".editor-save-status").wait_for(); page.locator(".editor:not([inert])").wait_for(state="attached")
    assert 'Immediate navigation' in page.locator('#note-blocks').inner_text()
    print('PASS immediate navigation/reload',flush=True)
    # All PATCH attempts fail while independent metadata operations still succeed.
    failing=True
    def patch_route(route):
     if route.request.method=='PATCH' and failing: route.fulfill(status=503,body='simulated failure')
     else: route.continue_()
    page.route('**/api/notes/browser-note',patch_route)
    page.locator('#note-blocks [contenteditable="true"]').first.fill('Keep my unsaved text')
    page.locator('.editor-save-status[data-state="save_failed"]').wait_for()
    page.locator('#note-info').click()
    page.locator('#inspector-tag-input').fill('browser-tag')
    page.locator('#inspector-tag-form button[type="submit"]').click()
    page.locator("#inspector-tags").get_by_text("browser-tag", exact=False).wait_for()
    assert 'Keep my unsaved text' in page.locator('#note-blocks').inner_text()
    page.locator('#inspector-link-target').select_option('related-note')
    page.locator('#inspector-link-form button[type="submit"]').click()
    page.locator("#inspector-links").get_by_text("Related note", exact=False).wait_for()
    assert 'Keep my unsaved text' in page.locator('#note-blocks').inner_text()
    print('PASS metadata refresh preserves unsaved text',flush=True)
    page.locator('#file-input').set_input_files({'name': 'browser-attachment.txt', 'mimeType': 'text/plain', 'buffer': b'Attachment while text is dirty'})
    page.locator('#note-blocks').get_by_text('Attachment while text is dirty', exact=False).wait_for()
    assert 'Keep my unsaved text' in page.locator('#note-blocks').inner_text()
    print('PASS upload preserves unsaved text',flush=True)
    failing=False
    page.locator('.editor-save-status').click()
    page.locator(".editor-save-status:disabled").wait_for()
    page.reload();page.locator(".editor-save-status").wait_for(); page.locator(".editor:not([inert])").wait_for(state="attached")
    assert 'Keep my unsaved text' in page.locator('#note-blocks').inner_text()
    print('PASS failed PATCH/retry/reload',flush=True)
    # Recovery after browser reload while the network remains unavailable for PATCH.
    failing=True
    page.locator('#note-blocks [contenteditable="true"]').first.fill('Recover after failed save')
    page.locator('.editor-save-status[data-state="save_failed"]').wait_for()
    page.on('dialog',lambda dialog: dialog.accept())
    page.reload();page.locator(".editor-save-status").wait_for(); page.locator(".editor:not([inert])").wait_for(state="attached")
    assert 'Recover after failed save' in page.locator('#note-blocks').inner_text()
    failing=False
    page.locator('.editor-save-status').click()
    page.locator(".editor-save-status:disabled").wait_for()
    print('PASS persistent recovery',flush=True)
    # Stub only the model response; draft commit and subsequent edit use real endpoints.
    draft=[{'type':'insert_block','noteId':'browser-note','block':{'id':'ai-e2e','type':'paragraph','data':{'parts':[{'text':'AI generated text'}]}}}]
    events='data: '+json.dumps({'type':'reply','text':'Draft ready'})+'\n\n'+'data: '+json.dumps({'type':'draft','draft':draft})+'\n\n'
    page.route('**/api/chat/stream',lambda route:route.fulfill(status=200,content_type='text/event-stream',body=events))
    page.locator('#fab-ai').click()
    page.locator('#ai-chat-input').fill('Create test draft')
    page.locator('#ai-chat-send').click()
    page.locator('.ai-draft-btn--apply').click()
    page.locator('.ai-draft-preview--applied').wait_for()
    page.locator('[data-close-chat]').click()
    page.locator('#note-blocks [data-block-id="ai-e2e"][contenteditable="true"], #note-blocks [data-block-id="ai-e2e"] [contenteditable="true"]').fill('AI then human edit')
    page.locator('.editor-save-status:disabled').wait_for()
    page.reload(); page.locator('.editor-save-status').wait_for(); page.locator('.editor:not([inert])').wait_for(state='attached')
    assert 'AI then human edit' in page.locator('#note-blocks').inner_text()
    print('PASS AI draft/commit/manual edit/reload',flush=True)
    page.screenshot(path='/tmp/ovc-stabilization-editor.png',full_page=False)
    csrf=next(cookie['value'] for cookie in context.cookies() if cookie['name']=='csrf_token')
    # Recovery must clone actual FileAsset references, not just inline text uploads.
    attached=context.request.post('/api/upload?noteId=browser-note',headers={'X-CSRF-Token':csrf},
        multipart={'files':{'name':'recover.md','mimeType':'text/markdown','buffer':b'# Recovery attachment'}})
    assert attached.status==200,attached.text()
    detail=context.request.get('/api/notes/browser-note').json()
    attachment_blocks=attached.json()['blocks']
    from app.services.sync_protocol import file_ids
    original_files=file_ids(attachment_blocks)
    assert original_files
    saved=context.request.patch('/api/notes/browser-note',headers={'X-CSRF-Token':csrf},
        data={'blocks':detail['blocks']+attachment_blocks})
    assert saved.status==200,saved.text()
    original_files=file_ids(saved.json()['blocks'])
    original_contents=sorted(context.request.get(f'/files/{fid}/original').body() for fid in original_files)
    page.reload();page.locator('.editor-save-status').wait_for();page.locator('.editor:not([inert])').wait_for(state='attached')
    remote=context.request.patch('/api/notes/browser-note',data={'title':'Changed from another tab'},headers={'X-CSRF-Token':csrf})
    assert remote.status==200,remote.text()
    page.locator('#note-blocks [contenteditable="true"]').first.fill('Local conflicting text must survive')
    page.locator('.editor-save-status[data-state="save_failed"]').wait_for()
    page.locator('.editor-save-status').click()
    page.wait_for_url(re.compile(r'/notes/(?!browser-note)[^/]+$'))
    page.locator('.editor:not([inert])').wait_for(state='attached')
    assert 'Local conflicting text must survive' in page.locator('#note-blocks').inner_text()
    assert context.request.get('/api/notes/browser-note').json()['title']=='Changed from another tab'
    copy_id=page.url.rsplit('/',1)[-1]
    copy=context.request.get('/api/notes/'+copy_id).json()
    copied_files=file_ids(copy['blocks'])
    assert len(copied_files)==len(original_files) and copied_files.isdisjoint(original_files), (copied_files,original_files)
    assert sorted(context.request.get(f'/files/{fid}/original').body() for fid in copied_files)==original_contents
    for fid in copied_files:
     assert context.request.get(f'/files/{fid}/original').status==200
    assert context.request.delete('/api/notes/browser-note',headers={'X-CSRF-Token':csrf}).status==200
    for fid in copied_files:
     assert context.request.get(f'/files/{fid}/original').status==200
    assert sorted(context.request.get(f'/files/{fid}/original').body() for fid in copied_files)==original_contents
    for fid in original_files:
     assert context.request.get(f'/files/{fid}/original').status==404
    print('PASS stale-version recovery preserves both notes and independent attachments after original tombstone',flush=True)
    page.locator('#note-blocks [contenteditable="true"]').first.fill('Saved before logout')
    page.locator('#auth-logout').click()
    page.wait_for_url('**/login')
    assert context.request.post('/auth/login',data={'identifier':'browser-user','password':'Browser123!'}).status==200
    csrf=next(cookie['value'] for cookie in context.cookies() if cookie['name']=='csrf_token')
    refreshed=context.request.post('/auth/refresh',headers={'X-CSRF-Token':csrf})
    assert refreshed.status==200,refreshed.text()
    saved_copy=context.request.get('/api/notes/'+copy_id,headers={'Authorization':'Bearer '+refreshed.json()['accessToken']})
    assert saved_copy.status==200,saved_copy.text()
    assert saved_copy.json()['blocks'][0]['data']['parts'][0]['text']=='Saved before logout'
    print('PASS logout flushes pending text',flush=True)
    assert not errors,errors
    browser.close()
  finally:
   proc.terminate();proc.wait(timeout=10);engine.dispose()
