"""Isolated real-server/browser/crash/performance checks. Never uses live DB/storage."""
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='ovc-runtime-e2e-') as temp:
        tmp = Path(temp)
        os.environ.update(DATABASE_URL=f'sqlite:///{tmp}/test.db', OVC_UPLOAD_ROOT=str(tmp/'uploads'),
            AUTH_MODE='local', APP_ENV='test', DESKTOP_MODE='false', SYNC_MODE='off', SYNC_ENABLED='false',
            SYNC_REMOTE_BASE_URL='', SYNC_BEARER_TOKEN='', PUBLIC_MODE='false', PUBLIC_BASE_URL='',
            COOKIE_SECURE='false', COOKIE_SAMESITE='lax', GROQ_API_KEY='',
            SECRET_KEY='isolated-runtime-browser-secret-never-real', PYTHONDONTWRITEBYTECODE='1',
            DB_AUTO_MIGRATE='false', OVC_ISOLATED_TESTS='1', ALLOWED_HOSTS='', TRUSTED_PROXY_IPS='')
        sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
        from app.db.session import engine, get_session
        from app.db.migrate import upgrade
        from app.main import app
        from app.db.models import Note, FileAsset
        from app.models.user import User
        from app.core.security import hash_password, create_access_token
        from test_upload_api import make_wav, make_simple_docx
        upgrade(engine)
        with get_session() as session:
            session.add(User(id='runtime-user',username='runtime-user',password_hash=hash_password('Runtime123!'),is_active=True))
            session.add(Note(id='runtime-note',user_id='runtime-user',title='Runtime test',blocks_json='[]'))
        engine.dispose()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        # This hook exists only in the disposable server module; never in production code.
        module=tmp/'stage6_server.py'
        module.write_text('''from app.main import app
from app.services import upload_pipeline
import json,sys
original = upload_pipeline.run_tool
def delayed(args, **kwargs):
    spec = json.loads(open(args[-1]).read())
    if spec.get('original_name') == 'crash.txt':
        source = "from app.services.conversion_worker import main;import os,time,pathlib,sys;pathlib.Path(sys.argv[1]).with_name('child.pid').write_text(str(os.getpid()));time.sleep(10);main()"
        args = [sys.executable,'-c',source,args[-1]]
    return original(args, **kwargs)
upload_pipeline.run_tool = delayed
''')
        env=dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp),str(ROOT/'src')]))
        log=(tmp/'server.log').open('w')
        def start():
            proc=subprocess.Popen([sys.executable,'-B','-m','uvicorn','stage6_server:app','--host','127.0.0.1','--port',str(port),'--no-access-log','--no-proxy-headers','--timeout-graceful-shutdown','5'],cwd=ROOT,env=env,stdout=log,stderr=log)
            for _ in range(150):
                try:
                    if httpx.get(base+'/readyz',timeout=.4).status_code==200:return proc
                except httpx.HTTPError:pass
                if proc.poll() is not None:raise RuntimeError((tmp/'server.log').read_text())
                time.sleep(.1)
            proc.kill();proc.wait();raise RuntimeError('isolated server not ready')
        proc=start()
        try:
            headers={'Authorization':'Bearer '+create_access_token('runtime-user')}
            with httpx.Client(base_url=base,headers=headers,timeout=20) as client:
                timings={}
                def measure(name,fn,count=10):
                    values=[]
                    for _ in range(count):
                        t=time.perf_counter();response=fn();values.append((time.perf_counter()-t)*1000)
                        assert response.status_code==200,(name,response.text)
                    timings[name]={'median_ms':round(statistics.median(values),2),'p95_ms':round(sorted(values)[max(0,int(.95*len(values)+.999)-1)],2),'samples':count}
                measure('GET notes',lambda:client.get('/api/notes'))
                measure('PATCH note',lambda:client.patch('/api/notes/runtime-note',json={'title':'Runtime test'}))
                measure('search',lambda:client.get('/api/notes/search/full',params={'q':'Runtime'}))
                measure('readyz',lambda:client.get('/readyz'))
                measure('small upload',lambda:client.post('/api/upload?noteId=runtime-note',files={'files':('small.txt',b'bounded upload','text/plain')}),5)
                measure('DOCX conversion',lambda:client.post('/api/upload?noteId=runtime-note',files={'files':('document.docx',make_simple_docx(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')}),5)
                response=client.post('/api/upload?noteId=runtime-note',files={'files':('seek.wav',make_wav(3),'audio/wav')})
                assert response.status_code==200,response.text
                audio_id=response.json()['files'][0]['id']
                from app.services.runtime import run_tool
                clip=tmp/'seek.webm'
                run_tool(['ffmpeg','-y','-f','lavfi','-i','color=c=blue:s=160x120:r=10','-t','3',
                          '-c:v','libvpx','-an',str(clip)],timeout=10)
                response=client.post('/api/upload?noteId=runtime-note',files={'files':('seek.webm',clip.read_bytes(),'video/webm')})
                assert response.status_code==200,response.text
                video_id=response.json()['files'][0]['id']
                print('PERFORMANCE '+json.dumps(timings),flush=True)
            capture=tmp/'capture.wav';capture.write_bytes(make_wav(3))
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=os.getenv("OVC_BROWSER_HEADED") != "1",args=[f'--use-file-for-fake-audio-capture={capture}', '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--autoplay-policy=no-user-gesture-required'])
                context=browser.new_context(base_url=base,permissions=['microphone'])
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                synthetic = os.getenv('OVC_BROWSER_SYNTHETIC_MIC') == '1'
                if synthetic:
                    # Only replace the capture source. Real MediaRecorder, uploader,
                    # HTTP, conversion and editor insertion still run unchanged.
                    context.add_init_script('navigator.mediaDevices.getUserMedia = async () => {\n                        const ctx = new AudioContext(); const dest = ctx.createMediaStreamDestination();\n                        const oscillator = ctx.createOscillator(); oscillator.connect(dest); oscillator.start();\n                        ctx.resume(); return dest.stream;\n                    };')
                page=context.new_page()
                page.on('pageerror',lambda e:print('PAGE_ERROR '+str(e),flush=True))
                login=context.request.post('/auth/login',data={'identifier':'runtime-user','password':'Runtime123!'})
                assert login.status==200,login.text()
                page.goto(base+'/notes/runtime-note')
                page.locator('.editor-save-status').wait_for()
                page.locator('.editor:not([inert])').wait_for(state='attached')
                assert page.evaluate("document.featurePolicy.allowsFeature('microphone')")

                page.locator('#fab-voice').click()
                page.wait_for_timeout(1000)
                page.locator('#fab-voice[aria-pressed="true"]').wait_for()
                page.wait_for_timeout(700)
                with page.expect_response(lambda r:'/api/upload' in r.url and r.request.method=='POST',timeout=20000) as uploaded:
                    page.locator('#fab-voice').click()
                assert uploaded.value.status==200,uploaded.value.text()
                print('PASS browser '+('synthetic audio source' if synthetic else 'virtual microphone')+' -> MediaRecorder -> real WebM upload/conversion',flush=True)
                seeking=page.evaluate('''async id => {
                    const audio = document.createElement('audio'); audio.src='/files/'+id+'/stream';document.body.append(audio);
                    await new Promise((resolve,reject)=>{audio.onloadedmetadata=resolve;audio.onerror=reject;});

                    await new Promise((resolve,reject)=>{audio.onseeked=resolve;audio.onerror=reject;audio.currentTime=1.5;});
                    return {time:audio.currentTime,duration:audio.duration};
                }''',audio_id)
                assert abs(seeking['time']-1.5)<.1 and seeking['duration']>=2.9
                print('PASS browser audio seeking / Range',flush=True)
                seeking=page.evaluate('''async id => {
                    const video=document.createElement('video');video.src='/files/'+id+'/video/source';document.body.append(video);
                    await new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=reject;});
                    await new Promise((resolve,reject)=>{video.onseeked=resolve;video.onerror=reject;video.currentTime=1.5;});
                    return video.currentTime;
                }''',video_id)
                assert abs(seeking-1.5)<.1
                print('PASS browser video seeking / Range',flush=True)
                browser.close()
            # Interrupt a real staged conversion, restart on SAME disposable DB.
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(1) as pool:
                def crash_upload():
                    try:return httpx.post(base+'/api/upload?noteId=runtime-note',headers=headers,files={'files':('crash.txt',b'incomplete','text/plain')},timeout=15)
                    except httpx.HTTPError:return None
                request=pool.submit(crash_upload)
                marker=None
                for _ in range(100):
                    markers=list((tmp/'uploads').rglob('child.pid'))
                    if markers:marker=markers[0];break
                    time.sleep(.05)
                assert marker is not None,'conversion did not start'
                with httpx.Client(base_url=base,headers=headers,timeout=2) as responsive:
                    started=time.monotonic()
                    assert responsive.get('/api/notes').status_code==200
                    assert responsive.patch('/api/notes/runtime-note',json={'title':'saved during conversion'}).status_code==200
                    assert responsive.get('/healthz').status_code==200
                    assert responsive.get('/readyz').status_code==200
                    assert time.monotonic()-started<2
                print('PASS real HTTP server responds during slow conversion',flush=True)
                child=int(marker.read_text());proc.kill();proc.wait(timeout=5);request.result(timeout=5)
                for _ in range(60):
                    try:os.kill(child,0)
                    except ProcessLookupError:break
                    time.sleep(.1)
                else:raise AssertionError('converter survived parent crash')
            proc=start()
            with httpx.Client(base_url=base,headers=headers,timeout=5) as client:
                assert client.get('/readyz').status_code==200
                assert client.get('/api/notes/runtime-note').status_code==200
                assert client.get('/files/incomplete/original').status_code==404
            with get_session() as session:
                assert session.query(FileAsset).filter_by(filename='crash.txt').count()==0
            with engine.connect() as connection:
                assert connection.exec_driver_sql('PRAGMA quick_check').scalar()=='ok'
                assert connection.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
            assert marker.exists(),'unknown staging files must not be automatically deleted'
            print('PASS abrupt kill / conversion child reaped / restart / stale staging not published / FK clean',flush=True)
        finally:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=15)
            log.close();engine.dispose()

if __name__=='__main__':main()
