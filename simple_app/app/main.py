import logging
from fastapi import FastAPI, Request
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
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.core.security import CSRF_COOKIE, get_user_from_refresh_cookie, issue_csrf_token
from app.core.config import settings

# OVC: pdf - проверяем доступность библиотек при старте
from app.services.files import HAS_PYMUPDF, HAS_PDF2IMAGE

logger = logging.getLogger(__name__)

# OVC: video - увеличиваем лимит размера запроса до 500MB
MAX_REQUEST_SIZE = 500 * 1024 * 1024  # 500MB

app = FastAPI(title="OVC Simple App", version="0.1.0")

# OVC: pdf - логируем статус библиотек при старте
@app.on_event("startup")
async def startup_event():
    logger.info(f"PDF rendering libraries: PyMuPDF={HAS_PYMUPDF}, pdf2image={HAS_PDF2IMAGE}")
    if not HAS_PYMUPDF and not HAS_PDF2IMAGE:
        logger.warning("PDF rendering not available! Install pymupdf: pip install pymupdf")

app.include_router(chat_router, prefix="/api")
app.include_router(commit_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(resolve_router, prefix="/api")
app.include_router(files_router)
app.include_router(auth_router)
app.include_router(users_router, prefix="/api")

app.mount("/static", StaticFiles(directory="simple_app/static"), name="static")
templates = Jinja2Templates(directory="simple_app/templates")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'"
    )
    return response


def _require_user(request: Request):
    try:
        return get_user_from_refresh_cookie(request)
    except Exception:
        return None


@app.get("/")
def index(request: Request, note_id: str = None):
    user = _require_user(request)
    if not user:
        return RedirectResponse(url="/login")
    response = templates.TemplateResponse("editor.html", {"request": request, "note_id": note_id, "user": user})
    _ensure_csrf_cookie(request, response)
    return response


@app.get("/notes")
def notes_page(request: Request):
    user = _require_user(request)
    if not user:
        return RedirectResponse(url="/login")
    response = templates.TemplateResponse("notes.html", {"request": request, "user": user})
    _ensure_csrf_cookie(request, response)
    return response


@app.get("/notes/{note_id}")
def note_page(request: Request, note_id: str):
    user = _require_user(request)
    if not user:
        return RedirectResponse(url="/login")
    response = templates.TemplateResponse("editor.html", {"request": request, "note_id": note_id, "user": user})
    _ensure_csrf_cookie(request, response)
    return response


@app.get("/graph")
def graph_page(request: Request):
    user = _require_user(request)
    if not user:
        return RedirectResponse(url="/login")
    response = templates.TemplateResponse("graph.html", {"request": request, "user": user})
    _ensure_csrf_cookie(request, response)
    return response


@app.get("/change-password")
def change_password_page(request: Request):
    user = _require_user(request)
    if not user:
        return RedirectResponse(url="/login")
    response = templates.TemplateResponse("auth/change-password.html", {"request": request, "user": user})
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
