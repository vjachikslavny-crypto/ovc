from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env file from project root (try multiple locations)
_config_dir = Path(__file__).resolve().parent
_possible_env_paths = [
    _config_dir.parents[3] / ".env",  # OVC/.env (from src/app/core)
    _config_dir.parents[2] / ".env",  # OVC/src/.env (legacy fallback)
    Path.cwd() / ".env",              # Current working directory
    Path.home() / "OVC" / ".env",     # Explicit path
]

for _env_path in _possible_env_paths:
    if _env_path.exists():
        # Keep shell/exported vars higher priority than .env defaults.
        load_dotenv(_env_path, override=False)
        break

AuthMode = Literal["none", "local", "supabase", "both"]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.database_url = (
            os.getenv("DATABASE_URL")
            or os.getenv("SIMPLE_DB_URL")
            or "sqlite:///./src/ovc.db"
        )
        self.secret_key = os.getenv(
            "SECRET_KEY", "CHANGE_ME_CHANGE_ME_CHANGE_ME_CHANGE_ME"
        )
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY должен быть не короче 32 символов.")
        self.access_token_expires_min = int(os.getenv("ACCESS_TOKEN_EXPIRES_MIN", "15"))
        self.refresh_token_expires_days = int(os.getenv("REFRESH_TOKEN_EXPIRES_DAYS", "30"))
        self.cookie_domain = os.getenv("COOKIE_DOMAIN") or None
        self.cookie_secure = _env_bool("COOKIE_SECURE", False)
        self.cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax")
        self.rate_limit_window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.rate_limit_max = int(os.getenv("RATE_LIMIT_MAX", "60"))
        self.password_min_length = int(os.getenv("PASSWORD_MIN_LENGTH", "6"))
        self.password_require_upper = _env_bool("PASSWORD_REQUIRE_UPPER", False)
        self.password_require_lower = _env_bool("PASSWORD_REQUIRE_LOWER", False)
        self.password_require_digit = _env_bool("PASSWORD_REQUIRE_DIGIT", False)
        self.password_require_symbol = _env_bool("PASSWORD_REQUIRE_SYMBOL", False)
        self.email_from = os.getenv("EMAIL_FROM", "no-reply@ovc.local")
        self.email_backend = os.getenv("EMAIL_BACKEND", "mock")
        self.desktop_mode = _env_bool("DESKTOP_MODE", False)
        self.sync_enabled = _env_bool("SYNC_ENABLED", False)
        self.sync_remote_base_url = os.getenv("SYNC_REMOTE_BASE_URL", "").strip()
        self.sync_bearer_token = os.getenv("SYNC_BEARER_TOKEN", "").strip()
        self.sync_poll_seconds = int(os.getenv("SYNC_POLL_SECONDS", "15"))
        self.sync_outbox_max = int(os.getenv("SYNC_OUTBOX_MAX", "10000"))
        self.sync_batch_size = int(os.getenv("SYNC_BATCH_SIZE", "100"))
        self.sync_request_timeout_seconds = float(
            os.getenv("SYNC_REQUEST_TIMEOUT_SECONDS", "12")
        )
        self.sync_pull_enabled = _env_bool("SYNC_PULL_ENABLED", True)
        
        # Auth mode: "none" | "local" | "supabase" | "both"
        self.auth_mode: AuthMode = os.getenv("AUTH_MODE", "local").lower()  # type: ignore
        if self.auth_mode not in ("none", "local", "supabase", "both"):
            self.auth_mode = "local"
        
        # Supabase configuration
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        self.supabase_issuer = os.getenv(
            "SUPABASE_ISSUER",
            f"{self.supabase_url}/auth/v1" if self.supabase_url else ""
        ).strip().rstrip("/")
        self.supabase_jwks_url = os.getenv(
            "SUPABASE_JWKS_URL",
            f"{self.supabase_url}/auth/v1/.well-known/jwks.json" if self.supabase_url else ""
        ).strip()
        self.supabase_jwt_aud = os.getenv("SUPABASE_JWT_AUD", "authenticated")
        
        # Validate Supabase config if mode requires it
        if self.auth_mode in ("supabase", "both"):
            if not self.supabase_url or not self.supabase_anon_key:
                raise ValueError(
                    "SUPABASE_URL and SUPABASE_ANON_KEY required when AUTH_MODE is 'supabase' or 'both'"
                )


settings = Settings()
