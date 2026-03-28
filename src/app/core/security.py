from __future__ import annotations

import base64
import datetime as dt
import hashlib
import logging
import re
import secrets
from typing import Any, Optional

from argon2 import PasswordHasher
from argon2.low_level import Type
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import HTTPException, Request
from jose import JWTError, jwt

from app.core.config import settings
from app.db.session import get_session
from app.models.session import RefreshToken
from app.models.user import User

logger = logging.getLogger(__name__)


JWT_ALG = "HS256"
CSRF_COOKIE = "csrf_token"
REFRESH_COOKIE = "refresh_token"
ACCESS_COOKIE = "ovc_access_token"
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9._-]{3,24}$')
FORBIDDEN_USERNAMES = {'admin', 'root', 'system', 'api', 'auth', 'login', 'register', 'logout', 'me'}

_ph = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception as exc:
        logger.warning("Password verify failed due to unexpected hash error: %s", exc)
        return False


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def create_access_token(subject: str, *, extra_claims: Optional[dict[str, Any]] = None) -> str:
    issued_at = _now()
    expires = issued_at + dt.timedelta(minutes=settings.access_token_expires_min)
    payload = {
        "sub": subject,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(16),
    }
    if extra_claims:
        reserved = {"sub", "iat", "exp", "jti", "aud", "iss"}
        for key, value in extra_claims.items():
            if key in reserved or value is None:
                continue
            payload[key] = value
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALG])
        logger.info(f"[AUTH-DEBUG] Token decoded successfully. Payload: {payload}")
        return payload
    except JWTError as exc:
        logger.error(f"[AUTH-DEBUG] Failed to decode token: {exc}")
        raise HTTPException(status_code=401, detail="Invalid access token") from exc


def _pepper() -> bytes:
    return settings.secret_key.encode("utf-8")


def hash_refresh_token(raw_token: str) -> str:
    digest = hashlib.sha256(raw_token.encode("utf-8") + _pepper()).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def get_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    cookie_token = request.cookies.get(ACCESS_COOKIE)
    if cookie_token:
        return cookie_token.strip()
    query_token = request.query_params.get("access_token")
    if query_token:
        return query_token.strip()
    return None


def require_csrf(request: Request) -> None:
    header = request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or header != cookie:
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def get_current_user(request: Request) -> User:
    """
    Get current user - uses auth provider system based on AUTH_MODE.
    """
    from app.core.config import settings
    
    # In desktop mode we also use the provider layer to allow explicit local offline fallback.
    if settings.desktop_mode or settings.auth_mode in ("supabase", "both", "none"):
        from app.core.auth_provider import get_current_user_from_provider
        return get_current_user_from_provider(request)
    
    # Default: local-only mode (original behavior)
    token = get_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token")
    with get_session() as session:
        user = session.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="User inactive")
        request.state.auth_context = "local-user"
        return user


def get_user_from_refresh_cookie(request: Request) -> User:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    token_hash = hash_refresh_token(raw_token)
    now = _now()
    with get_session() as session:
        token = (
            session.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.rotated_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .first()
        )
        if not token:
            raise HTTPException(status_code=401, detail="Refresh token invalid")
        user = session.get(User, token.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="User inactive")
        return user


def get_current_user_or_refresh(request: Request) -> User:
    # Prefer bearer/cookie token, but gracefully fallback to refresh cookie when token is stale.
    token = get_bearer_token(request)
    if token:
        try:
            return get_current_user(request)
        except HTTPException:
            pass
    return get_user_from_refresh_cookie(request)


def validate_username(username: str) -> bool:
    """Валидация username: 3-24 символа, только a-z, 0-9, ., _, -"""
    if not username or not USERNAME_REGEX.match(username):
        return False
    if username.lower() in FORBIDDEN_USERNAMES:
        return False
    return True


def check_user_locked(user: User) -> tuple[bool, Optional[dt.datetime]]:
    """Проверка, заблокирован ли пользователь"""
    if user.locked_until and user.locked_until > _now():
        return True, user.locked_until
    return False, None


def register_login_failure(session, user: User, max_failures: int = 10) -> None:
    """Регистрация неудачной попытки входа. Блокирует аккаунт после max_failures попыток."""
    user.failed_login_count += 1
    if user.failed_login_count >= max_failures:
        user.locked_until = _now() + dt.timedelta(minutes=15)
    session.add(user)


def reset_login_failures(session, user: User) -> None:
    """Сброс счетчика неудачных попыток входа"""
    user.failed_login_count = 0
    user.locked_until = None
    session.add(user)
