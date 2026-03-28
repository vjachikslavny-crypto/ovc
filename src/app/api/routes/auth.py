from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings
from app.core.auth_provider import supabase_auth_get_user, get_current_user_from_provider
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    issue_csrf_token,
    require_csrf,
    verify_password,
    validate_username,
    check_user_locked,
    register_login_failure,
    reset_login_failures,
    get_current_user,
)
from app.db.session import get_session
from app.models.session import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    AuthOkResponse,
    ForgotRequest,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    ChangePasswordRequest,
)
from app.services.audit import log_event
from app.services.email import send_verification_email
from app.services.password_policy import password_policy_hint, validate_password
from app.services.rate_limit import LoginLockout, RateLimiter
from sqlalchemy import text, func, or_
from pathlib import Path

router = APIRouter(tags=["auth"])

# Определяем путь к templates относительно каталога src
# auth.py -> routes -> api -> app -> src
BASE_DIR = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_rate_limiter = RateLimiter()
_login_lock = LoginLockout()
_USERNAME_SANITIZE_RE = re.compile(r"[^a-z0-9._-]+")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key)


def _build_verify_link(request: Request, token: str) -> str:
    if settings.public_base_url:
        base = settings.public_base_url.rstrip("/")
        return f"{base}/auth/verify?token={token}"
    return str(request.url_for("auth_verify").include_query_params(token=token))


def _ensure_email_verified_column(session) -> None:
    try:
        dialect = session.bind.dialect.name
        if dialect == "sqlite":
            rows = session.execute(text("PRAGMA table_info(users)")).fetchall()
            columns = {row[1] for row in rows}
            if "email_verified_at" not in columns:
                session.execute(text("ALTER TABLE users ADD COLUMN email_verified_at DATETIME"))
        else:
            session.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP")
            )
    except Exception:
        # Keep auth flow operational even if migration isn't applied yet.
        pass


def _cookie_secure_for_request(request: Request) -> bool:
    """
    Keep secure cookies for public HTTPS, but allow localhost HTTP dev login.
    """
    if not settings.cookie_secure:
        return False

    host = (request.headers.get("host") or "").split(":", 1)[0].lower()
    if host in {"127.0.0.1", "localhost"}:
        return False

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"

    if request.url.scheme:
        return request.url.scheme.lower() == "https"

    return True


def _set_refresh_cookie_for_request(request: Request, response: Response, raw_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        raw_token,
        httponly=True,
        secure=_cookie_secure_for_request(request),
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=settings.refresh_token_expires_days * 86400,
        path="/",
    )


def _set_csrf_cookie_for_request(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=_cookie_secure_for_request(request),
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=settings.refresh_token_expires_days * 86400,
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, domain=settings.cookie_domain, path="/")
    response.delete_cookie(CSRF_COOKIE, domain=settings.cookie_domain, path="/")
    response.delete_cookie(ACCESS_COOKIE, domain=settings.cookie_domain, path="/")


def _fingerprint_hash(request: Request) -> Optional[str]:
    if not request:
        return None
    raw = f"{request.client.host if request.client else ''}|{request.headers.get('user-agent', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _auth_template_context(request: Request) -> dict:
    """Build common context for auth templates."""
    return {
        "request": request,
        "user": None,
        "auth_mode": settings.auth_mode,
        "supabase_url": settings.supabase_url if settings.auth_mode in ("supabase", "both") else "",
        "supabase_anon_key": settings.supabase_anon_key if settings.auth_mode in ("supabase", "both") else "",
        "password_min_length": settings.password_min_length,
        "password_policy_hint": password_policy_hint(),
    }


def _normalize_username_candidate(raw: str) -> str:
    value = (raw or "").strip().lower()
    value = _USERNAME_SANITIZE_RE.sub("-", value).strip("._-")
    if len(value) < 3:
        value = "user"
    return value[:24]


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded_for or "unknown"


def _username_exists(session, username: str) -> bool:
    return session.query(User).filter(func.lower(User.username) == username.lower()).first() is not None


def _build_unique_username(session, email: str, explicit_username: Optional[str]) -> str:
    base_raw = explicit_username or email.split("@", 1)[0]
    base = _normalize_username_candidate(base_raw)
    if not validate_username(base):
        base = "user"

    candidate = base
    suffix = 1
    while _username_exists(session, candidate) or not validate_username(candidate):
        suffix_text = f"-{suffix}"
        prefix = base[: max(3, 24 - len(suffix_text))]
        candidate = f"{prefix}{suffix_text}"[:24]
        suffix += 1
        if suffix > 9999:
            candidate = f"user-{dt.datetime.now(dt.timezone.utc).timestamp():.0f}"[:24]
            break
    return candidate


@router.get("/login", response_class=HTMLResponse)
def login_view(request: Request):
    return templates.TemplateResponse("auth/login.html", _auth_template_context(request))


@router.get("/register", response_class=HTMLResponse)
def register_view(request: Request):
    return templates.TemplateResponse("auth/register.html", _auth_template_context(request))


@router.get("/auth/verify", name="auth_verify")
def auth_verify(token: str, request: Request):
    try:
        data = _serializer().loads(token, salt="email-verify", max_age=60 * 60 * 24)
    except SignatureExpired:
        return RedirectResponse(url="/login?verify=expired", status_code=302)
    except BadSignature:
        return RedirectResponse(url="/login?verify=invalid", status_code=302)

    user_id = str(data.get("sub") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    if not user_id:
        return RedirectResponse(url="/login?verify=invalid", status_code=302)

    with get_session() as session:
        _ensure_email_verified_column(session)
        user = session.get(User, user_id)
        if not user:
            return RedirectResponse(url="/login?verify=invalid", status_code=302)
        if email and (user.email or "").lower() != email:
            return RedirectResponse(url="/login?verify=invalid", status_code=302)

        session.execute(
            text("UPDATE users SET email_verified_at = :ts WHERE id = :uid"),
            {"ts": dt.datetime.now(dt.timezone.utc), "uid": user.id},
        )
        log_event(session, "EMAIL_VERIFIED", user_id=user.id, request=request)

    return RedirectResponse(url="/login?verified=1", status_code=302)




@router.post("/auth/register", response_model=AuthOkResponse, status_code=201)
def register(payload: RegisterRequest, request: Request):
    if not _rate_limiter.allow(
        f"register:{_client_ip(request)}",
        settings.rate_limit_register_per_min,
        60,
    ):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте позже.")

    email_lower = payload.email.lower().strip()
    if not email_lower:
        raise HTTPException(status_code=400, detail="Email обязателен")
    
    # Валидация пароля
    errors = validate_password(payload.password)
    if errors:
        raise HTTPException(status_code=400, detail=" ".join(errors))

    with get_session() as session:
        _ensure_email_verified_column(session)
        email_exists = session.query(User).filter(
            func.lower(User.email) == email_lower
        ).first()
        if email_exists:
            log_event(session, "REGISTER_EMAIL_EXISTS", request=request, metadata={"email": payload.email})
            raise HTTPException(status_code=409, detail="Email уже используется")

        username = _build_unique_username(session, email_lower, payload.username)

        user = User(
            username=username,
            email=email_lower,
            password_hash=hash_password(payload.password)
        )
        session.add(user)
        session.flush()
        log_event(session, "REGISTER_SUCCESS", user_id=user.id, request=request)

        # При первом пользователе привязываем старые заметки/файлы
        user_count = session.query(User).count()
        if user_count == 1:
            try:
                session.execute(text("UPDATE notes SET user_id = :uid WHERE user_id IS NULL"), {"uid": user.id})
            except Exception:
                pass  # Таблица может не иметь user_id или быть пустой
            try:
                session.execute(text("UPDATE files SET user_id = :uid WHERE user_id IS NULL"), {"uid": user.id})
            except Exception:
                pass  # Таблица может не существовать или не иметь user_id
            log_event(session, "LEGACY_DATA_MIGRATED", user_id=user.id, request=request)

        verify_token = _serializer().dumps(
            {"sub": str(user.id), "email": email_lower},
            salt="email-verify",
        )
        verify_link = _build_verify_link(request, verify_token)
        send_verification_email(user, verify_link)
        log_event(session, "EMAIL_VERIFY_SENT", user_id=user.id, request=request)

    return AuthOkResponse(ok=True)


@router.post("/auth/resend-verification", response_model=AuthOkResponse)
def resend_verification(payload: ForgotRequest, request: Request):
    email_lower = payload.email.lower().strip()
    if not email_lower:
        return AuthOkResponse(ok=True, detail="Если email существует, письмо отправлено.")

    limiter_key = f"resend-verify:{_client_ip(request)}:{email_lower}"
    if not _rate_limiter.allow(limiter_key, 1, 60):
        raise HTTPException(status_code=429, detail="Подождите минуту перед повторной отправкой")

    with get_session() as session:
        _ensure_email_verified_column(session)
        user = session.query(User).filter(func.lower(User.email) == email_lower).first()
        if user:
            verify_token = _serializer().dumps(
                {"sub": str(user.id), "email": email_lower},
                salt="email-verify",
            )
            verify_link = _build_verify_link(request, verify_token)
            send_verification_email(user, verify_link)
            log_event(session, "EMAIL_VERIFY_RESENT", user_id=user.id, request=request)

    # Anti-enumeration response.
    return AuthOkResponse(ok=True, detail="Если email существует, письмо отправлено.")


@router.post("/auth/login", response_model=AuthOkResponse)
def login(payload: LoginRequest, request: Request, response: Response):
    if not _rate_limiter.allow(
        f"login:{_client_ip(request)}",
        settings.rate_limit_login_per_min,
        60,
    ):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте позже.")

    identifier = payload.identifier.strip().lower()

    with get_session() as session:
        # Ищем пользователя по username ИЛИ email (case-insensitive)
        user = session.query(User).filter(
            or_(
                func.lower(User.username) == identifier,
                func.lower(User.email) == identifier
            )
        ).first()
        
        if not user or not user.is_active:
            log_event(session, "LOGIN_FAIL", request=request, metadata={"identifier": identifier})
            raise HTTPException(status_code=401, detail="Неверные учетные данные")
        
        # Проверка lockout
        locked, until = check_user_locked(user)
        if locked:
            log_event(session, "LOGIN_LOCKED", user_id=user.id, request=request, metadata={"locked_until": str(until)})
            raise HTTPException(status_code=423, detail=f"Аккаунт заблокирован до {until.strftime('%H:%M')}")
        
        # Проверка пароля
        if not verify_password(payload.password, user.password_hash):
            register_login_failure(session, user, max_failures=10)
            log_event(session, "LOGIN_FAIL", user_id=user.id, request=request)
            raise HTTPException(status_code=401, detail="Неверные учетные данные")
        
        # Успешный вход - сброс счетчиков
        reset_login_failures(session, user)

        raw_token = generate_refresh_token()
        token_hash = hash_refresh_token(raw_token)
        expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=settings.refresh_token_expires_days)
        refresh = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires,
            fingerprint_hash=_fingerprint_hash(request),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        session.add(refresh)
        log_event(session, "LOGIN_SUCCESS", user_id=user.id, request=request)

    _set_refresh_cookie_for_request(request, response, raw_token)
    csrf_token = issue_csrf_token()
    _set_csrf_cookie_for_request(request, response, csrf_token)
    return AuthOkResponse(ok=True)


@router.post("/auth/supabase/session", response_model=AuthOkResponse)
def supabase_session_bridge(request: Request, response: Response):
    """
    Create local refresh/csrf cookies from a valid Supabase access token.
    Required for server-side endpoints consumed outside fetch wrapper
    (e.g. media/file URLs in <img>/<audio>/<video>) and stable web sessions.
    """
    if settings.auth_mode not in ("supabase", "both"):
        raise HTTPException(status_code=400, detail="Supabase auth mode is not enabled")

    sb_user = supabase_auth_get_user(request)
    if not sb_user:
        raise HTTPException(status_code=401, detail="Missing Supabase access token")

    # Resolves/creates local user link using existing provider logic.
    user = get_current_user_from_provider(request)
    now = dt.datetime.now(dt.timezone.utc)
    raw_token = generate_refresh_token()
    token_hash = hash_refresh_token(raw_token)
    expires = now + dt.timedelta(days=settings.refresh_token_expires_days)

    with get_session() as session:
        refresh = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires,
            fingerprint_hash=_fingerprint_hash(request),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        session.add(refresh)
        log_event(
            session,
            "SUPABASE_SESSION_BRIDGE",
            user_id=user.id,
            request=request,
            metadata={"supabase_user_id": sb_user.id},
        )

    _set_refresh_cookie_for_request(request, response, raw_token)
    csrf_token = issue_csrf_token()
    _set_csrf_cookie_for_request(request, response, csrf_token)
    return AuthOkResponse(ok=True)


@router.post("/auth/refresh", response_model=RefreshResponse)
def refresh(request: Request, response: Response):
    require_csrf(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    token_hash = hash_refresh_token(raw_token)
    now = dt.datetime.now(dt.timezone.utc)

    with get_session() as session:
        token = session.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        if not token:
            raise HTTPException(status_code=401, detail="Refresh token invalid")
        if token.revoked_at:
            raise HTTPException(status_code=401, detail="Refresh token revoked")
        if token.rotated_at:
            # Повторное использование — отзываем всю семью токенов.
            session.query(RefreshToken).filter(RefreshToken.user_id == token.user_id).update(
                {"revoked_at": now}
            )
            log_event(session, "TOKEN_REUSE", user_id=token.user_id, request=request)
            raise HTTPException(status_code=401, detail="Refresh token reused")
        # Преобразуем naive datetime из БД в aware для корректного сравнения
        expires_at = token.expires_at.replace(tzinfo=dt.timezone.utc) if token.expires_at.tzinfo is None else token.expires_at
        if expires_at <= now:
            raise HTTPException(status_code=401, detail="Refresh token expired")

        token.rotated_at = now
        raw_next = generate_refresh_token()
        next_hash = hash_refresh_token(raw_next)
        next_expires = now + dt.timedelta(days=settings.refresh_token_expires_days)
        session.add(
            RefreshToken(
                user_id=token.user_id,
                token_hash=next_hash,
                expires_at=next_expires,
                fingerprint_hash=_fingerprint_hash(request),
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        log_event(session, "TOKEN_ROTATE", user_id=token.user_id, request=request)

        user = session.get(User, token.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="User inactive")

    _set_refresh_cookie_for_request(request, response, raw_next)
    csrf_token = issue_csrf_token()
    _set_csrf_cookie_for_request(request, response, csrf_token)
    access_token = create_access_token(
        str(user.id),
        extra_claims={
            "email": user.email,
            "username": user.username,
        },
    )
    return RefreshResponse(accessToken=access_token)


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    require_csrf(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        with get_session() as session:
            token = session.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
            if token and not token.revoked_at:
                token.revoked_at = dt.datetime.now(dt.timezone.utc)
                log_event(session, "LOGOUT", user_id=token.user_id, request=request)
    _clear_cookies(response)
    return Response(status_code=204)




@router.get("/auth/username-available")
def check_username_availability(u: str):
    """Проверка доступности username"""
    if not u or len(u) < 3:
        return {"available": False, "reason": "too_short"}
    
    if not validate_username(u):
        return {"available": False, "reason": "invalid_format"}
    
    with get_session() as session:
        exists = session.query(User).filter(
            func.lower(User.username) == u.lower()
        ).first()
        return {"available": not exists}


@router.post("/auth/change-password", response_model=AuthOkResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Смена пароля для авторизованного пользователя"""
    require_csrf(request)
    
    errors = validate_password(payload.new_password)
    if errors:
        raise HTTPException(status_code=400, detail=" ".join(errors))
    
    with get_session() as session:
        user = session.get(User, current_user.id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Проверка старого пароля
        if not verify_password(payload.old_password, user.password_hash):
            log_event(session, "PASSWORD_CHANGE_FAIL", user_id=user.id, request=request)
            raise HTTPException(status_code=401, detail="Неверный текущий пароль")
        
        # Установка нового пароля
        user.password_hash = hash_password(payload.new_password)
        
        # Отзываем все refresh tokens (заставляем перелогиниться везде)
        now = dt.datetime.now(dt.timezone.utc)
        session.query(RefreshToken).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None)
        ).update({"revoked_at": now})
        
        log_event(session, "PASSWORD_CHANGE_SUCCESS", user_id=user.id, request=request)
    
    return AuthOkResponse(ok=True)
