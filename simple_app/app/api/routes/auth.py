from __future__ import annotations

import datetime as dt
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
# itsdangerous не используется в username-based auth
# from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings
from app.core.security import (
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
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    ChangePasswordRequest,
)
from app.services.audit import log_event
# Email services не используются в username-based auth
# from app.services.email import send_password_reset, send_verification_email
from app.services.password_policy import validate_password
from app.services.rate_limit import LoginLockout, RateLimiter
from sqlalchemy import text, func, or_
from pathlib import Path

router = APIRouter(tags=["auth"])

# Определяем путь к templates относительно корня проекта
# auth.py -> routes -> api -> app -> simple_app -> OVC (корень)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "simple_app" / "templates"))

_rate_limiter = RateLimiter()
_login_lock = LoginLockout()


# Serializer и link builders не используются в username-based auth
# def _serializer() -> URLSafeTimedSerializer:
#     return URLSafeTimedSerializer(settings.secret_key)
# 
# def _build_verify_link(request: Request, token: str) -> str:
#     return str(request.url_for("auth_verify").include_query_params(token=token))
# 
# def _build_reset_link(request: Request, token: str) -> str:
#     return str(request.url_for("auth_reset_view").include_query_params(token=token))


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        raw_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=settings.refresh_token_expires_days * 86400,
        path="/",
    )


def _set_csrf_cookie(response: Response, token: str) -> None:
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


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, domain=settings.cookie_domain, path="/")
    response.delete_cookie(CSRF_COOKIE, domain=settings.cookie_domain, path="/")


def _fingerprint_hash(request: Request) -> Optional[str]:
    if not request:
        return None
    raw = f"{request.client.host if request.client else ''}|{request.headers.get('user-agent', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.get("/login", response_class=HTMLResponse)
def login_view(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request, "user": None})


@router.get("/register", response_class=HTMLResponse)
def register_view(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request, "user": None})




@router.post("/auth/register", response_model=AuthOkResponse, status_code=201)
def register(payload: RegisterRequest, request: Request):
    if not _rate_limiter.allow(f"register:{request.client.host}", 10, 60):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте позже.")

    username = payload.username.strip()
    
    # Валидация username
    if not validate_username(username):
        raise HTTPException(
            status_code=400,
            detail="Username должен содержать только a-z, 0-9, ., _, - (3-24 символа) и не быть зарезервированным"
        )
    
    # Валидация пароля
    errors = validate_password(payload.password)
    if errors:
        raise HTTPException(status_code=400, detail=" ".join(errors))

    with get_session() as session:
        # Проверка username (case-insensitive)
        existing = session.query(User).filter(
            func.lower(User.username) == username.lower()
        ).first()
        if existing:
            log_event(session, "REGISTER_USERNAME_EXISTS", request=request, metadata={"username": username})
            raise HTTPException(status_code=409, detail="Username уже занят")
        
        # Проверка email (если указан)
        if payload.email:
            email_lower = payload.email.lower()
            email_exists = session.query(User).filter(
                func.lower(User.email) == email_lower
            ).first()
            if email_exists:
                log_event(session, "REGISTER_EMAIL_EXISTS", request=request, metadata={"email": payload.email})
                raise HTTPException(status_code=409, detail="Email уже используется")

        user = User(
            username=username,
            email=payload.email.lower() if payload.email else None,
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

    return AuthOkResponse(ok=True)


@router.post("/auth/login", response_model=AuthOkResponse)
def login(payload: LoginRequest, request: Request, response: Response):
    if not _rate_limiter.allow(f"login:{request.client.host}", 10, 60):
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

    _set_refresh_cookie(response, raw_token)
    csrf_token = issue_csrf_token()
    _set_csrf_cookie(response, csrf_token)
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

    _set_refresh_cookie(response, raw_next)
    csrf_token = issue_csrf_token()
    _set_csrf_cookie(response, csrf_token)
    access_token = create_access_token(str(user.id))
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
