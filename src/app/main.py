import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse

from app.api.chat import router as chat_router
from app.api.commit import router as commit_router
from app.api.export import router as export_router
from app.api.files import router as files_router
from app.api.graph import router as graph_router
from app.api.notes import router as notes_router
from app.api.upload import router as upload_router
from app.api.resolve import router as resolve_router
from app.api.sync import router as sync_router
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.core.security import (
    CSRF_COOKIE,
    create_access_token,
    get_user_from_refresh_cookie,
    issue_csrf_token,
)
from app.core.config import settings
from app.services.sync_engine import start_sync_worker_once

# OVC: pdf - проверяем доступность библиотек при старте
from app.services.files import HAS_PYMUPDF, HAS_PDF2IMAGE

logger = logging.getLogger(__name__)

# OVC: video - увеличиваем лимит размера запроса до 500MB
MAX_REQUEST_SIZE = 500 * 1024 * 1024  # 500MB

app = FastAPI(title="OVC Simple App", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OVC: pdf - логируем статус библиотек при старте
@app.on_event("startup")
async def startup_event():
    logger.info(f"PDF rendering libraries: PyMuPDF={HAS_PYMUPDF}, pdf2image={HAS_PDF2IMAGE}")
    if not HAS_PYMUPDF and not HAS_PDF2IMAGE:
        logger.warning("PDF rendering not available! Install pymupdf: pip install pymupdf")
    try:
        from app.db.migrate import upgrade

        upgrade()
    except Exception as exc:
        logger.warning("Schema migration failed on startup: %s", exc)
    logger.info("runtime config: %s", settings.runtime_summary())
    for warning in settings.startup_warnings:
        logger.warning("config warning: %s", warning)
    start_sync_worker_once()

app.include_router(chat_router, prefix="/api")
app.include_router(commit_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(resolve_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(files_router)
app.include_router(auth_router)
app.include_router(users_router, prefix="/api")

BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Add auth_mode to global template context
templates.env.globals["auth_mode"] = settings.auth_mode
templates.env.globals["desktop_mode"] = settings.desktop_mode


def _default_port_for_scheme(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _same_host(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    aliases = {
        "127.0.0.1": {"127.0.0.1", "localhost"},
        "localhost": {"127.0.0.1", "localhost"},
    }
    if a == b:
        return True
    return b in aliases.get(a, set()) or a in aliases.get(b, set())


def _origin_from_url(value: str) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except Exception:
        return None
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _build_csp_header() -> str:
    script_src = ["'self'", "https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net", "https://www.instagram.com"]
    style_src = ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"]
    img_src = ["'self'", "data:", "blob:", "https:", "https://i.ytimg.com"]
    connect_src = ["'self'"]
    font_src = ["'self'", "data:", "https://fonts.gstatic.com"]
    media_src = ["'self'", "data:", "blob:", "https:"]
    frame_src = [
        "'self'",
        "https://www.youtube-nocookie.com",
        "https://www.youtube.com",
        "https://www.instagram.com",
        "https://www.tiktok.com",
    ]

    for candidate in (
        settings.supabase_url,
        settings.sync_remote_base_url,
        settings.public_base_url,
    ):
        origin = _origin_from_url(candidate)
        if origin:
            connect_src.append(origin)
            if origin.startswith("https://"):
                connect_src.append(f"wss://{origin[len('https://'):]}")

    script_src.extend(settings.csp_script_src_extra)
    style_src.extend(settings.csp_style_src_extra)
    connect_src.extend(settings.csp_connect_src_extra)
    img_src.extend(settings.csp_img_src_extra)
    frame_src.extend(settings.csp_frame_src_extra)

    directives = {
        "default-src": ["'self'"],
        "script-src": _dedupe(script_src),
        "style-src": _dedupe(style_src),
        "img-src": _dedupe(img_src),
        "connect-src": _dedupe(connect_src),
        "font-src": _dedupe(font_src),
        "media-src": _dedupe(media_src),
        "frame-src": _dedupe(frame_src),
        "object-src": ["'none'"],
        "frame-ancestors": ["'none'"],
    }

    return " ".join(
        f"{name} {' '.join(values)};"
        for name, values in directives.items()
    )


async def _proxy_remote_file_if_needed(request: Request, response):
    """
    Desktop-only fallback:
    if local /files/* returns 404, fetch same path from SYNC_REMOTE_BASE_URL.
    This keeps web behavior unchanged and lets desktop render server-side attachments.
    """
    if not settings.desktop_mode:
        return response
    if request.method.upper() != "GET":
        return response
    if response.status_code != 404:
        return response
    if not request.url.path.startswith("/files/"):
        return response

    remote_base = (settings.sync_remote_base_url or "").strip().rstrip("/")
    if not remote_base:
        return response

    try:
        remote = urlsplit(remote_base)
    except Exception:
        return response

    req_port = request.url.port or _default_port_for_scheme(request.url.scheme or "http")
    remote_port = remote.port or _default_port_for_scheme(remote.scheme or "http")
    if _same_host(request.url.hostname, remote.hostname) and req_port == remote_port:
        # Avoid proxy loops when remote points to current backend.
        return response

    target = f"{remote_base}{request.url.path}"
    if request.url.query:
        target += f"?{request.url.query}"

    proxy_headers = {}
    for header_name in (
        "range",
        "accept",
        "if-none-match",
        "if-modified-since",
        "user-agent",
    ):
        value = request.headers.get(header_name)
        if value:
            proxy_headers[header_name] = value

    if settings.sync_bearer_token:
        proxy_headers["authorization"] = f"Bearer {settings.sync_bearer_token}"
    else:
        try:
            proxy_user = get_user_from_refresh_cookie(request)
            proxy_headers["authorization"] = f"Bearer {create_access_token(str(proxy_user.id))}"
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(
            timeout=settings.sync_request_timeout_seconds,
            follow_redirects=True,
        ) as client:
            proxied = await client.get(target, headers=proxy_headers)
    except Exception as exc:
        logger.warning("remote file proxy failed for %s: %s", target, exc)
        return response

    if proxied.status_code >= 400:
        return response

    passthrough_headers = {}
    for header_name in (
        "cache-control",
        "etag",
        "last-modified",
        "content-disposition",
        "content-range",
        "accept-ranges",
    ):
        value = proxied.headers.get(header_name)
        if value:
            passthrough_headers[header_name] = value

    return Response(
        content=proxied.content,
        status_code=proxied.status_code,
        headers=passthrough_headers,
        media_type=proxied.headers.get("content-type"),
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response = await _proxy_remote_file_if_needed(request, response)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    csp_header_name = "Content-Security-Policy-Report-Only" if settings.csp_report_only else "Content-Security-Policy"
    response.headers[csp_header_name] = _build_csp_header()
    auth_context = getattr(request.state, "auth_context", None)
    if auth_context and settings.runtime_status_enabled:
        response.headers["X-OVC-Auth-Context"] = str(auth_context)
    return response


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _require_user(request: Request):
    try:
        return get_user_from_refresh_cookie(request)
    except Exception:
        return None


def _allow_anonymous() -> bool:
    if settings.desktop_mode and settings.allow_desktop_dev_fallback:
        return True
    return settings.auth_mode in ("none", "supabase", "both")


def _template_context(request: Request, user):
    return {
        "request": request,
        "user": user,
        "auth_mode": settings.auth_mode,
        "desktop_mode": settings.desktop_mode,
        "supabase_url": settings.supabase_url if settings.auth_mode in ("supabase", "both") else "",
        "supabase_anon_key": settings.supabase_anon_key if settings.auth_mode in ("supabase", "both") else "",
    }


@app.get("/")
def index(request: Request, note_id: str = None):
    user = _require_user(request)
    if not user and not _allow_anonymous():
        return RedirectResponse(url="/login")
    if not user and not settings.desktop_mode and settings.auth_mode != "none":
        response = templates.TemplateResponse("welcome.html", _template_context(request, user))
        _ensure_csrf_cookie(request, response)
        return response
    context = _template_context(request, user)
    context["note_id"] = note_id
    response = templates.TemplateResponse("editor.html", context)
    _ensure_csrf_cookie(request, response)
    return response


@app.get("/notes")
def notes_page(request: Request):
    user = _require_user(request)
    if not user and not _allow_anonymous():
        return RedirectResponse(url="/login")
    response = templates.TemplateResponse("notes.html", _template_context(request, user))
    _ensure_csrf_cookie(request, response)
    return response


@app.get("/notes/{note_id}")
def note_page(request: Request, note_id: str):
    user = _require_user(request)
    if not user and not _allow_anonymous():
        return RedirectResponse(url="/login")
    context = _template_context(request, user)
    context["note_id"] = note_id
    response = templates.TemplateResponse("editor.html", context)
    _ensure_csrf_cookie(request, response)
    return response


@app.get("/graph")
def graph_page(request: Request):
    user = _require_user(request)
    if not user and not _allow_anonymous():
        return RedirectResponse(url="/login")
    response = templates.TemplateResponse("graph.html", _template_context(request, user))
    _ensure_csrf_cookie(request, response)
    return response


@app.get("/change-password")
def change_password_page(request: Request):
    user = _require_user(request)
    if not user and not _allow_anonymous():
        return RedirectResponse(url="/login")
    response = templates.TemplateResponse("auth/change-password.html", _template_context(request, user))
    _ensure_csrf_cookie(request, response)
    return response


def _ensure_csrf_cookie(request: Request, response) -> None:
    if request.cookies.get(CSRF_COOKIE):
        return
    token = issue_csrf_token()
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=settings.refresh_token_expires_days * 86400,
        path="/",
    )


@app.get("/api/runtime/status")
def runtime_status(request: Request):
    if not settings.runtime_status_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    identity_type = "unauthenticated"
    identity_user_id = None
    try:
        from app.core.auth_provider import get_auth_user

        auth_user = get_auth_user(request)
        identity_type = auth_user.provider
        identity_user_id = auth_user.id
    except Exception:
        pass

    return {
        "ok": True,
        "config": settings.runtime_summary(),
        "request": {
            "authContext": getattr(request.state, "auth_context", None),
            "identityType": identity_type,
            "identityUserId": identity_user_id,
        },
    }
