"""Public URL redirects with DNS/IP validation and a pinned connection per hop."""
import http.client
import json
import os
from pathlib import Path
import sys
from app.services.runtime import run_tool
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlsplit, urljoin
from fastapi import HTTPException
from app.core.config import settings


def validate_public_url(url, allowed_hosts):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if (parsed.scheme != 'https' or parsed.username or parsed.password or
                parsed.port not in (None, 443) or host not in allowed_hosts):
            raise ValueError
    except ValueError:
        raise HTTPException(400, 'Unsupported public URL') from None
    return parsed


def public_addresses(host, deadline=None):
    deadline = deadline or time.monotonic() + settings.external_http_timeout_seconds
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HTTPException(504, 'URL resolution timed out')
    # OS DNS (including macOS/VPN split DNS) has no portable cancellation API.
    # Isolate only this call in a killable process instead of stranding a worker.
    resolver = ('import json,socket,sys;print(json.dumps(sorted({r[4][0] for r in '
                'socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)})))')
    try:
        result = run_tool([sys.executable, '-c', resolver, host], timeout=remaining)
        addresses = json.loads(result.stdout)
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise HTTPException(400, 'Non-public destination is not allowed')
        return sorted(addresses)
    except (OSError, ValueError, TypeError):
        raise HTTPException(502, 'Unable to resolve public destination') from None


def _resolve_public_redirect(url, allowed_hosts):
    deadline = time.monotonic() + settings.external_http_timeout_seconds
    for _ in range(6):
        parsed = validate_public_url(url, allowed_hosts)
        address = public_addresses(parsed.hostname, deadline)[0]
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise HTTPException(504, 'URL resolution timed out')
        conn = http.client.HTTPSConnection(parsed.hostname, timeout=remaining)
        try:
            # Resolve once, connect to that numeric address, retain TLS hostname
            # verification. Redirects are validated BEFORE opening the next socket.
            raw = socket.create_connection((address, 443), timeout=remaining)
            try:
                conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
            except BaseException:
                raw.close()
                raise
            target = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
            conn.request('HEAD', target, headers={'User-Agent':'OVC/1.0'})
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader('Location')
                if not location:
                    raise HTTPException(502, 'Invalid redirect')
                url = urljoin(url, location)
                continue
            if response.status >= 400:
                raise HTTPException(502, 'Public URL is unavailable')
            return url
        except (OSError, http.client.HTTPException):
            raise HTTPException(502, 'Unable to fetch public URL') from None
        finally:
            conn.close()
    raise HTTPException(502, 'Too many redirects')


def resolve_public_redirect(url, allowed_hosts):
    validate_public_url(url, allowed_hosts)
    env = dict(os.environ, OVC_CONVERSION_CHILD='1',
               PYTHONPATH=str(Path(__file__).resolve().parents[2]), PYTHONDONTWRITEBYTECODE='1')
    result = run_tool([sys.executable, '-m', 'app.services.public_url', url,
        json.dumps(sorted(allowed_hosts))], timeout=settings.external_http_timeout_seconds, env=env)
    response = json.loads(result.stdout)
    if 'error' in response:
        raise HTTPException(response['status'], response['error'])
    return response['url']


if __name__ == '__main__':
    try:
        result = {'url': _resolve_public_redirect(sys.argv[1], set(json.loads(sys.argv[2])))}
    except HTTPException as exc:
        result = {'status': exc.status_code, 'error': exc.detail}
    print(json.dumps(result))
