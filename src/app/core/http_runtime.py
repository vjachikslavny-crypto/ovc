"""Small ASGI boundary: body budgets, explicit proxy trust, safe diagnostics."""
import asyncio
import json
import tempfile
import threading
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from app.services.storage import require_space, storage_error
import logging
import re
import time
import uuid
from starlette.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.core.config import settings

logger = logging.getLogger(__name__)
_upload_slots = threading.BoundedSemaphore(settings.runtime_workers)


class RuntimeHTTPMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope['headers']}
        raw_id = headers.get(b'x-request-id', b'').decode('ascii', errors='ignore')
        request_id = raw_id if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', raw_id) else uuid.uuid4().hex
        scope.setdefault('state', {})['request_id'] = request_id
        total = 0
        status = 500
        response_started = False
        body_error = None
        error_sent = False
        body_complete = False
        start = time.monotonic()
        async def send_response(message):
            nonlocal status, error_sent, response_started
            if body_error is not None:
                data = json.dumps({"detail":body_error.detail}).encode()
                if message["type"] == "http.response.start":
                    message = dict(message, status=body_error.status_code, headers=[
                        (k,v) for k,v in message.get("headers", []) if k.lower() not in
                        {b"content-type", b"content-length", b"content-encoding"}] + [
                        (b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())])
                elif message["type"] == "http.response.body":
                    if error_sent:
                        return
                    message = {"type":"http.response.body", "body":data, "more_body":False}
                    error_sent = True
            if message['type'] == 'http.response.start':
                response_started = True
                status = message['status']
                response_headers = list(message.get('headers', []))
                present = {k.lower() for k, _ in response_headers}
                for key, value in ((b'x-content-type-options', b'nosniff'),
                        (b'x-frame-options', b'DENY'), (b'referrer-policy', b'strict-origin-when-cross-origin'),
                        (b'permissions-policy', b'microphone=(self), camera=(), geolocation=(), clipboard-read=(), clipboard-write=(self)')):
                    if key not in present:
                        response_headers.append((key, value))
                if not ({b'content-security-policy', b'content-security-policy-report-only'} & present):
                    from app.main import _build_csp_header
                    csp_name = b'content-security-policy-report-only' if settings.csp_report_only else b'content-security-policy'
                    response_headers.append((csp_name, _build_csp_header().encode()))
                message['headers'] = [(k,v) for k,v in response_headers if k.lower() != b'x-request-id'] + [(b'x-request-id', request_id.encode())]
            await send(message)
        limit = settings.max_request_bytes
        # JSON/form metadata does not need the large multipart budget.
        multipart = b'multipart/form-data' in headers.get(b'content-type', b'')
        if not multipart:
            limit = min(limit, settings.max_ai_context_chars * 4 + 1024 * 1024)
        try:
            length = int(headers.get(b'content-length', b'0'))
            if length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({'detail':'Invalid Content-Length'}, 400)(scope, receive, send_response)
        if length > limit:
            return await JSONResponse({'detail':'Request body too large'}, 413)(scope, receive, send_response)
        if multipart and not _upload_slots.acquire(blocking=False):
            return await JSONResponse({'detail':'Upload capacity busy; retry later'}, 503,
                headers={'Retry-After':'2'})(scope, receive, send_response)
        async def bounded_receive():
            nonlocal total, body_error, body_complete
            if body_complete:
                return await receive()
            try:
                remaining = settings.request_body_timeout_seconds - (time.monotonic()-start)
                message = await asyncio.wait_for(receive(), max(0, remaining))
            except asyncio.TimeoutError:
                body_error = HTTPException(408, 'Request body timed out')
                raise body_error
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > limit:
                    body_error = HTTPException(413, 'Request body too large')
                    raise body_error
                if multipart:
                    try:
                        await run_in_threadpool(require_space, tempfile.gettempdir(), len(message.get('body', b'')))
                    except HTTPException as exc:
                        body_error = exc
                        raise
                body_complete = not message.get('more_body', False)
            return message
        try:
            # Trust only explicitly configured peers. Launch scripts disable
            # uvicorn's outer proxy rewriting, so the socket peer is still intact.
            app = ProxyHeadersMiddleware(self.app, trusted_hosts=settings.trusted_proxy_ips)
            await app(scope, bounded_receive, send_response)
        except Exception as exc:
            # Do not let Uvicorn print private exception values in a traceback.
            if response_started:
                logger.error('stream_interrupted id=%s type=%s', request_id, type(exc).__name__)
                raise RuntimeError('Response stream interrupted') from None
            from app.main import unhandled_error
            from starlette.requests import Request
            response = await unhandled_error(Request(scope), exc)
            await response(scope, receive, send_response)
        finally:
            if multipart:
                _upload_slots.release()
            if status >= 400:
                # No query string, credentials, payload or raw exception message.
                logger.warning('request_failed id=%s status=%s duration_ms=%d',
                               request_id, status, (time.monotonic()-start)*1000)
