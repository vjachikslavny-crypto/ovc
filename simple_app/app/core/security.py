from __future__ import annotations

import base64
import datetime as dt
import hashlib
import logging
import re
import secrets
from typing import Optional

from argon2 import PasswordHasher
from argon2.low_level import Type
from argon2.exceptions import VerifyMismatchError
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
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9._-]{3,24}$')
FORBIDDEN_USERNAMES = {'admin', 'root', 'system', 'api', 'auth', 'login', 'register', 'logout', 'me'}

_ph = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def create_access_token(subject: str) -> str:
    issued_at = _now()
    expires = issued_at + dt.timedelta(minutes=settings.access_token_expires_min)
    payload = {
        "sub": subject,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(16),
    }
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
    return None


def require_csrf(request: Request) -> None:
    header = request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or header != cookie:
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def get_current_user(request: Request) -> User:
    token = get_bearer_token(request)
    logger.info(f"[AUTH-DEBUG] get_current_user - token present: {token is not None}")
    if not token:
        logger.warning("[AUTH-DEBUG] No bearer token in request")
        raise HTTPException(status_code=401, detail="Missing access token")
    logger.info(f"[AUTH-DEBUG] Bearer token (first 20 chars): {token[:20]}...")
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    logger.info(f"[AUTH-DEBUG] User ID from token: {user_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token")
    with get_session() as session:
        user = session.get(User, user_id)
        logger.info(f"[AUTH-DEBUG] User found: {user is not None}, active: {user.is_active if user else 'N/A'}")
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="User inactive")
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
    token = get_bearer_token(request)
    if token:
        return get_current_user(request)
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
