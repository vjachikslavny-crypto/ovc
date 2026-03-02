"""
Pluggable authentication providers for OVC.

Supports:
- LocalAuthProvider: existing local JWT auth
- SupabaseAuthProvider: Supabase JWT with JWKS verification
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import httpx
from fastapi import HTTPException, Request
from jose import jwt, JWTError, jwk
from jose.exceptions import JWKError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.session import get_session
from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class AuthUser:
    """Unified user object returned by auth providers."""
    id: str
    email: Optional[str] = None
    provider: str = "local"  # "local" or "supabase"
    raw_claims: Optional[Dict[str, Any]] = None


# ============================================================================
# JWKS Cache for Supabase
# ============================================================================

class JWKSCache:
    """In-memory JWKS cache with TTL."""
    
    def __init__(self, ttl_seconds: int = 600):  # 10 minutes default
        self._keys: Dict[str, Any] = {}
        self._fetched_at: float = 0
        self._ttl = ttl_seconds
    
    def is_expired(self) -> bool:
        return time.time() - self._fetched_at > self._ttl
    
    def get_key(self, kid: str) -> Optional[Any]:
        if self.is_expired():
            return None
        return self._keys.get(kid)
    
    def update(self, jwks_data: Dict[str, Any]) -> None:
        self._keys = {}
        for key_data in jwks_data.get("keys", []):
            kid = key_data.get("kid")
            if kid:
                try:
                    self._keys[kid] = jwk.construct(key_data)
                except JWKError as e:
                    logger.warning(f"Failed to construct JWK for kid={kid}: {e}")
        self._fetched_at = time.time()
        logger.info(f"JWKS cache updated with {len(self._keys)} keys")


_jwks_cache = JWKSCache()


def _fetch_jwks() -> None:
    """Fetch JWKS from Supabase and update cache."""
    if not settings.supabase_jwks_url:
        logger.error("SUPABASE_JWKS_URL not configured")
        return
    
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(settings.supabase_jwks_url)
            response.raise_for_status()
            _jwks_cache.update(response.json())
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        raise HTTPException(status_code=503, detail="Auth service unavailable")


def _is_supabase_issuer(issuer: str) -> bool:
    if not issuer:
        return False
    expected = (settings.supabase_issuer or "").rstrip("/")
    if expected and issuer.rstrip("/") == expected:
        return True
    # Legacy/older Supabase tokens can carry simplified issuer values.
    if issuer == "supabase":
        return True
    base = (settings.supabase_url or "").rstrip("/")
    return bool(base and issuer.startswith(base))


def _verify_supabase_token_via_userinfo(token: str) -> AuthUser:
    """
    Validate Supabase access token via Supabase Auth API.
    Works as a compatibility fallback when local JWT checks are insufficient.
    """
    base = (settings.supabase_url or "").rstrip("/")
    if not base or not settings.supabase_anon_key:
        raise HTTPException(status_code=503, detail="Supabase configuration is incomplete")

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{base}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key,
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("Supabase /auth/v1/user request failed: %s", exc)
        raise HTTPException(status_code=503, detail="Auth service unavailable") from exc

    if response.status_code in (401, 403):
        logger.warning(
            "Supabase /auth/v1/user unauthorized (%s): %s",
            response.status_code,
            (response.text or "")[:200],
        )
        raise HTTPException(status_code=401, detail="Invalid Supabase token")
    if response.status_code >= 400:
        logger.warning("Supabase /auth/v1/user returned %s", response.status_code)
        raise HTTPException(status_code=503, detail="Auth service unavailable")

    data = response.json()
    user_id = data.get("id") or data.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Supabase token has no subject")

    return AuthUser(
        id=str(user_id),
        email=data.get("email"),
        provider="supabase",
        raw_claims=data,
    )


def _get_signing_key(token: str) -> Any:
    """Get the signing key for a JWT token."""
    try:
        headers = jwt.get_unverified_header(token)
    except JWTError as e:
        logger.warning(f"Failed to get JWT headers: {e}")
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    kid = headers.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token missing kid header")
    
    # Try cache first
    key = _jwks_cache.get_key(kid)
    if key:
        return key
    
    # Refresh cache
    _fetch_jwks()
    
    key = _jwks_cache.get_key(kid)
    if not key:
        raise HTTPException(status_code=401, detail="Unknown signing key")
    
    return key


# ============================================================================
# Local Auth Provider
# ============================================================================

def get_bearer_token(request: Request) -> Optional[str]:
    """Extract access token from Authorization header, cookie, or query."""
    auth = request.headers.get("Authorization") or ""
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    cookie_token = request.cookies.get("ovc_access_token")
    if cookie_token:
        return cookie_token.strip()
    query_token = request.query_params.get("access_token")
    if query_token:
        return query_token.strip()
    return None


def local_auth_get_user(request: Request) -> Optional[AuthUser]:
    """
    Authenticate using local JWT tokens.
    Returns AuthUser if valid, None if no token present, raises HTTPException on invalid token.
    """
    from app.core.security import decode_access_token
    
    token = get_bearer_token(request)
    if not token:
        return None
    
    try:
        payload = decode_access_token(token)
    except HTTPException:
        # Token invalid - let caller decide how to handle
        raise
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid access token")
    
    with get_session() as session:
        user = session.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="User inactive")
        
        return AuthUser(
            id=str(user.id),
            email=user.email,
            provider="local",
            raw_claims=payload
        )


# ============================================================================
# Supabase Auth Provider
# ============================================================================

def supabase_auth_get_user(request: Request) -> Optional[AuthUser]:
    """
    Authenticate using Supabase JWT tokens.
    Returns AuthUser if valid, None if no token present, raises HTTPException on invalid token.
    """
    token = get_bearer_token(request)
    if not token:
        return None
    
    # Check token algorithm and validate through the suitable strategy.
    try:
        headers = jwt.get_unverified_header(token)
        alg = headers.get("alg", "")
    except JWTError:
        return None

    if alg == "HS256":
        # HS256 can be either local token or Supabase legacy token.
        # Distinguish by issuer when possible; if issuer is absent we still try
        # Supabase introspection to keep compatibility with legacy tokens.
        try:
            claims = jwt.get_unverified_claims(token)
        except JWTError:
            return None
        issuer = str(claims.get("iss") or "")
        if issuer and not _is_supabase_issuer(issuer):
            return None
        return _verify_supabase_token_via_userinfo(token)

    if alg not in ("ES256", "RS256"):
        # Unknown/changed algorithm: let Supabase API be the source of truth.
        return _verify_supabase_token_via_userinfo(token)

    # Asymmetric Supabase tokens: verify locally via JWKS.
    try:
        signing_key = _get_signing_key(token)
    except HTTPException:
        # If JWKS fetch/key lookup fails, fallback to Supabase API validation.
        return _verify_supabase_token_via_userinfo(token)

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[alg],
            audience=settings.supabase_jwt_aud,
            issuer=settings.supabase_issuer,
        )
    except JWTError as e:
        logger.warning(f"Supabase JWT verification failed, fallback to userinfo: {e}")
        return _verify_supabase_token_via_userinfo(token)

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing subject")

    return AuthUser(
        id=sub,
        email=payload.get("email"),
        provider="supabase",
        raw_claims=payload
    )


# ============================================================================
# Unified Auth Function
# ============================================================================

def get_auth_user(request: Request) -> AuthUser:
    """
    Get authenticated user based on AUTH_MODE setting.
    
    Modes:
    - "none": Returns a dev user (anonymous access)
    - "local": Uses local JWT auth only
    - "supabase": Uses Supabase JWT auth only
    - "both": Tries local first, then Supabase
    
    Raises HTTPException if authentication fails.
    """
    mode = settings.auth_mode
    has_access_token = bool(get_bearer_token(request))
    # Mode: none - anonymous/dev access
    if mode == "none":
        return AuthUser(id="dev-user", email=None, provider="none")
    
    # Mode: local only
    if mode == "local":
        try:
            user = local_auth_get_user(request)
        except HTTPException:
            # Desktop offline fallback is allowed only when no access token was provided.
            if settings.desktop_mode and not has_access_token:
                return AuthUser(id="dev-user", email=None, provider="none")
            raise
        if user:
            return user
        if settings.desktop_mode and not has_access_token:
            return AuthUser(id="dev-user", email=None, provider="none")
        raise HTTPException(status_code=401, detail="Missing access token")
    
    # Mode: supabase only
    if mode == "supabase":
        user = supabase_auth_get_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Missing Supabase access token")
        return user
    
    # Mode: both - try local first, then supabase
    if mode == "both":
        local_error: Optional[HTTPException] = None
        supabase_error: Optional[HTTPException] = None

        # Try local auth first (non-raising check)
        try:
            user = local_auth_get_user(request)
            if user:
                return user
        except HTTPException as exc:
            local_error = exc  # Local token invalid, try Supabase
        
        # Try Supabase auth
        try:
            user = supabase_auth_get_user(request)
            if user:
                return user
        except HTTPException as exc:
            supabase_error = exc  # Supabase token invalid too

        if supabase_error and supabase_error.status_code != 401:
            raise supabase_error
        if local_error and local_error.status_code != 401:
            raise local_error
        
        # No valid authentication found.
        # Desktop fallback is only for explicit offline/no-token usage.
        if settings.desktop_mode and not has_access_token:
            return AuthUser(id="dev-user", email=None, provider="none")
        raise HTTPException(status_code=401, detail="Missing or invalid access token")
    
    # Fallback - should not reach here
    raise HTTPException(status_code=500, detail="Invalid auth configuration")


def get_current_user_from_provider(request: Request) -> User:
    """
    Get the current User model from the database using the auth provider.
    
    For Supabase users, creates a local user record if not exists.
    """
    auth_user = get_auth_user(request)
    
    # Dev mode - return a mock user or first user
    if auth_user.provider == "none":
        with get_session() as session:
            user = session.query(User).first()
            if user:
                return user
            # Create dev user if no users exist
            user = User(
                username="dev-user",
                email="dev@localhost",
                password_hash="",
                is_active=True
            )
            session.add(user)
            session.flush()
            return user
    
    # Local auth - user ID is the actual DB user ID
    if auth_user.provider == "local":
        with get_session() as session:
            user = session.get(User, auth_user.id)
            if not user or not user.is_active:
                raise HTTPException(status_code=403, detail="User inactive")
            return user
    
    # Supabase auth - need to find or create local user record
    if auth_user.provider == "supabase":
        with get_session() as session:
            # Try to find user by supabase_id
            user = session.query(User).filter(
                User.supabase_id == auth_user.id
            ).first()
            
            if user:
                if not user.is_active:
                    raise HTTPException(status_code=403, detail="User inactive")
                return user
            
            # Try to link by email if exists
            if auth_user.email:
                email_lower = auth_user.email.lower()
                user = session.query(User).filter(
                    func.lower(User.email) == email_lower
                ).first()
                if user:
                    if not user.is_active:
                        raise HTTPException(status_code=403, detail="User inactive")
                    if not user.supabase_id:
                        user.supabase_id = auth_user.id
                        session.add(user)
                        session.flush()
                    return user
            
            # Create new user linked to Supabase
            username = f"sb_{auth_user.id[:8]}"  # Generate username from Supabase ID
            email = auth_user.email
            
            # Ensure unique username
            base_username = username
            counter = 1
            while session.query(User).filter(User.username == username).first():
                username = f"{base_username}_{counter}"
                counter += 1
            
            try:
                user = User(
                    username=username,
                    email=email,
                    password_hash="",  # No local password for Supabase users
                    supabase_id=auth_user.id,
                    is_active=True
                )
                session.add(user)
                session.flush()
                logger.info(f"Created local user {user.id} for Supabase user {auth_user.id}")
                return user
            except IntegrityError:
                session.rollback()
                user = session.query(User).filter(User.supabase_id == auth_user.id).first()
                if user:
                    return user
                if auth_user.email:
                    email_lower = auth_user.email.lower()
                    user = session.query(User).filter(
                        func.lower(User.email) == email_lower
                    ).first()
                    if user and not user.supabase_id:
                        user.supabase_id = auth_user.id
                        session.add(user)
                        session.flush()
                        return user
                raise HTTPException(status_code=500, detail="Failed to link Supabase user")
    
    raise HTTPException(status_code=500, detail="Unknown auth provider")
