from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env file from project root (try multiple locations)
_config_dir = Path(__file__).resolve().parent
_project_root = _config_dir.parents[2]  # .../OVC
_possible_env_paths = [
    _project_root / ".env",             # OVC/.env
    _project_root / "src" / ".env",     # OVC/src/.env (legacy fallback)
    Path.cwd() / ".env",                # Current working directory
    Path.home() / "OVC" / ".env",       # Explicit path
]

for _env_path in _possible_env_paths:
    if _env_path.exists():
        # Keep shell/exported vars higher priority than .env defaults.
        load_dotenv(_env_path, override=False)
        break

AuthMode = Literal["none", "local", "supabase", "both"]
SyncMode = Literal["off", "shared-db", "remote-sync", "remote-shell"]
_PROJECT_ROOT = _project_root
_DEFAULT_SQLITE_PATH = (_PROJECT_ROOT / "src" / "ovc.db").resolve()


def _normalize_database_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return f"sqlite:///{_DEFAULT_SQLITE_PATH}"

    # Normalize legacy relative sqlite paths so runs from any cwd use one DB.
    if value.startswith("sqlite:///./"):
        rel = value[len("sqlite:///./"):]
        return f"sqlite:///{(_PROJECT_ROOT / rel).resolve()}"

    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.startup_warnings: list[str] = []
        self.database_url = _normalize_database_url(
            os.getenv("DATABASE_URL")
            or os.getenv("SIMPLE_DB_URL")
            or ""
        )
        _DEFAULT_SECRET_KEY = "CHANGE_ME_CHANGE_ME_CHANGE_ME_CHANGE_ME"
        self.secret_key = os.getenv("SECRET_KEY", _DEFAULT_SECRET_KEY)
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY должен быть не короче 32 символов.")
        if self.secret_key == _DEFAULT_SECRET_KEY:
            _env = os.getenv("APP_ENV", "development").strip().lower()
            if _env == "production":
                raise ValueError(
                    "SECRET_KEY использует дефолтное значение. "
                    "Установите уникальный SECRET_KEY для production."
                )
            self.startup_warnings.append(
                "SECRET_KEY использует дефолтное значение — ОБЯЗАТЕЛЬНО замените перед production deploy"
            )
        self.access_token_expires_min = int(os.getenv("ACCESS_TOKEN_EXPIRES_MIN", "15"))
        self.refresh_token_expires_days = int(os.getenv("REFRESH_TOKEN_EXPIRES_DAYS", "30"))
        self.cookie_domain = os.getenv("COOKIE_DOMAIN") or None
        self.cookie_secure = _env_bool("COOKIE_SECURE", os.getenv("APP_ENV", "development").lower() == "production")
        self.cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax")
        self.cookie_samesite = self.cookie_samesite.lower()
        if self.cookie_samesite not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict or none")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        self.public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip()
        self.cors_origins = self._parse_cors_origins()
        self.rate_limit_window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.rate_limit_max = int(os.getenv("RATE_LIMIT_MAX", "60"))
        self.rate_limit_login_per_min = int(os.getenv("RATE_LIMIT_LOGIN_PER_MIN", "10"))
        self.rate_limit_register_per_min = int(
            os.getenv("RATE_LIMIT_REGISTER_PER_MIN", str(self.rate_limit_login_per_min))
        )
        self.password_min_length = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))
        if self.password_min_length < 6:
            self._warn("PASSWORD_MIN_LENGTH < 6 is unsafe; forcing 6")
            self.password_min_length = 6
        self.password_min_character_classes = int(
            os.getenv("PASSWORD_MIN_CHARACTER_CLASSES", "3")
        )
        if self.password_min_character_classes < 1:
            self.password_min_character_classes = 1
        if self.password_min_character_classes > 4:
            self.password_min_character_classes = 4
        self.password_require_upper = _env_bool("PASSWORD_REQUIRE_UPPER", False)
        self.password_require_lower = _env_bool("PASSWORD_REQUIRE_LOWER", False)
        self.password_require_digit = _env_bool("PASSWORD_REQUIRE_DIGIT", False)
        self.password_require_symbol = _env_bool("PASSWORD_REQUIRE_SYMBOL", False)
        self.email_from = os.getenv("EMAIL_FROM", "no-reply@ovc.local")
        self.email_backend = os.getenv("EMAIL_BACKEND", "mock")
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        self.db_auto_migrate = _env_bool("DB_AUTO_MIGRATE", False)
        if self.db_auto_migrate and self.app_env not in {"development", "test"}:
            raise ValueError("DB_AUTO_MIGRATE is allowed only in development/test; production requires explicit migrations")
        self.desktop_mode = _env_bool("DESKTOP_MODE", False)
        self.allow_desktop_dev_fallback = _env_bool(
            "ALLOW_DESKTOP_DEV_FALLBACK",
            False,
        )
        if self.allow_desktop_dev_fallback:
            self._warn(
                "ALLOW_DESKTOP_DEV_FALLBACK=true: desktop requests without token may use explicit dev user"
            )
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
        self.sync_mode: SyncMode = self._resolve_sync_mode(
            os.getenv("SYNC_MODE", "auto").strip().lower()
        )
        self.sync_remote_configured = bool(self.sync_remote_base_url)
        self.sync_worker_enabled = (
            self.sync_mode == "remote-sync"
            and bool(self.sync_bearer_token)
        )
        if self.sync_mode == "remote-sync" and not self.sync_bearer_token:
            self._warn(
                "SYNC_MODE=remote-sync but SYNC_BEARER_TOKEN is empty; "
                "background worker disabled (manual /api/sync/trigger still available with user token)"
            )
        
        # Auth mode: "none" | "local" | "supabase" | "both"
        self.auth_mode: AuthMode = os.getenv("AUTH_MODE", "local").lower()  # type: ignore
        if self.auth_mode not in ("none", "local", "supabase", "both"):
            raise ValueError("Unknown AUTH_MODE")
        
        self.public_mode = _env_bool("PUBLIC_MODE") or self.app_env == "production" or bool(self.public_base_url)
        if self.public_mode and self.auth_mode == "none":
            if not _env_bool("ALLOW_UNSAFE_PUBLIC_NO_AUTH"):
                raise ValueError("Public AUTH_MODE=none is unsafe; use authentication (override: ALLOW_UNSAFE_PUBLIC_NO_AUTH)")
            self._warn("DANGER: public authentication disabled by ALLOW_UNSAFE_PUBLIC_NO_AUTH")

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

        self.runtime_status_enabled = _env_bool(
            "RUNTIME_STATUS_ENABLED",
            self.desktop_mode or self.auth_mode == "none" or self.app_env != "production",
        )
        # LLM / Agent
        self.groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
        self.llm_model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2048"))
        self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.4"))
        self.llm_context_budget = int(os.getenv("LLM_CONTEXT_BUDGET", "6000"))
        self.llm_timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

        if not 0 < self.llm_timeout_seconds < 3600 or not 0 < self.sync_request_timeout_seconds < 3600:
            raise ValueError('AI and sync HTTP timeouts must be positive and finite (<3600s)')

        self.csp_report_only = _env_bool("CSP_REPORT_ONLY", False)
        self.csp_script_src_extra = self._parse_csv_env("CSP_SCRIPT_SRC_EXTRA")
        self.csp_style_src_extra = self._parse_csv_env("CSP_STYLE_SRC_EXTRA")
        self.csp_connect_src_extra = self._parse_csv_env("CSP_CONNECT_SRC_EXTRA")
        self.csp_img_src_extra = self._parse_csv_env("CSP_IMG_SRC_EXTRA")
        self.csp_frame_src_extra = self._parse_csv_env("CSP_FRAME_SRC_EXTRA")

        # Stage 6: finite per-process budgets, shared by HTTP and desktop callers.
        for name, default in {
            'MAX_REQUEST_BYTES': 510 * 1024 * 1024,
            'MAX_FILE_BYTES': 200 * 1024 * 1024,
            'MAX_CONVERSION_BYTES': 50 * 1024 * 1024,
            'MAX_PREVIEW_BYTES': 16 * 1024 * 1024,
            'MAX_ARCHIVE_EXPANDED_BYTES': 200 * 1024 * 1024,
            'MAX_AI_CONTEXT_CHARS': 100000,
            'MAX_UPLOAD_FILES': 10,
            'RUNTIME_WORKERS': 4,
            'SUBPROCESS_OUTPUT_BYTES': 65536,
            'RATE_LIMIT_UPLOAD_PER_MIN': 30,
            'RATE_LIMIT_AI_PER_MIN': 30,
            'RATE_LIMIT_SEARCH_PER_MIN': 120,
            'RATE_LIMIT_REFRESH_PER_MIN': 60,
        }.items():
            value = int(os.getenv(name, str(default)))
            if value <= 0:
                raise ValueError(f'{name} must be positive')
            setattr(self, name.lower(), value)
        self.storage_min_free_bytes = int(os.getenv('STORAGE_MIN_FREE_BYTES', str(128 * 1024 * 1024)))
        if self.storage_min_free_bytes < 0:
            raise ValueError('STORAGE_MIN_FREE_BYTES must be nonnegative')
        for name, default in {
            'RUNTIME_JOB_TIMEOUT_SECONDS': 150, 'CONVERSION_TIMEOUT_SECONDS': 90,
            'FFMPEG_TIMEOUT_SECONDS': 30, 'LIBREOFFICE_TIMEOUT_SECONDS': 60,
            'REQUEST_BODY_TIMEOUT_SECONDS': 30, 'EXTERNAL_HTTP_TIMEOUT_SECONDS': 10,
            'SHUTDOWN_GRACE_SECONDS': 5,
        }.items():
            value = float(os.getenv(name, str(default)))
            if not 0 < value < 3600:
                raise ValueError(f'{name} must be between 0 and 3600')
            setattr(self, name.lower(), value)
        self.trusted_proxy_ips = self._parse_csv_env('TRUSTED_PROXY_IPS')
        if '*' in self.trusted_proxy_ips:
            raise ValueError('TRUSTED_PROXY_IPS must contain explicit addresses/networks, not *')
        import ipaddress
        for peer in self.trusted_proxy_ips:
            if ipaddress.ip_network(peer, strict=False).prefixlen == 0:
                raise ValueError('TRUSTED_PROXY_IPS must not trust the entire Internet')
        self.allowed_hosts = self._parse_csv_env('ALLOWED_HOSTS')
        if '*' in self.cors_origins:
            raise ValueError('Wildcard CORS is incompatible with credentialed requests')
        if self.public_mode:
            from urllib.parse import urlsplit
            if not self.cookie_secure:
                raise ValueError('Public HTTPS requires COOKIE_SECURE=true')
            if self.allow_desktop_dev_fallback:
                raise ValueError('Public mode forbids desktop dev fallback')
            if not self.allowed_hosts or '*' in self.allowed_hosts:
                raise ValueError('Public mode requires explicit ALLOWED_HOSTS')
            if self.public_base_url:
                public = urlsplit(self.public_base_url)
                if public.scheme != 'https' or not public.hostname or public.username or public.password:
                    raise ValueError('PUBLIC_BASE_URL must be a valid HTTPS URL without credentials')
        if self.app_env == 'production' and self.db_auto_migrate:
            raise ValueError('Production migrations must be explicit')

    def _warn(self, message: str) -> None:
        self.startup_warnings.append(message)

    def _resolve_sync_mode(self, raw_mode: str) -> SyncMode:
        mode = raw_mode or "auto"
        if mode not in {"auto", "off", "shared-db", "remote-sync", "remote-shell"}:
            self._warn(f"Unknown SYNC_MODE='{mode}', falling back to auto")
            mode = "auto"

        if mode == "auto":
            if self.sync_remote_base_url:
                if self.sync_enabled:
                    return "remote-sync"
                if self.desktop_mode:
                    return "remote-shell"
                self._warn(
                    "SYNC_REMOTE_BASE_URL is set but both SYNC_ENABLED and DESKTOP_MODE are false; sync is off"
                )
                return "off"
            return "shared-db" if self.desktop_mode else "off"

        resolved: SyncMode = mode  # type: ignore[assignment]
        if resolved in {"remote-sync", "remote-shell"} and not self.sync_remote_base_url:
            raise ValueError(f"SYNC_MODE={resolved} requires SYNC_REMOTE_BASE_URL")
        if resolved == "remote-sync" and not self.sync_enabled:
            self._warn("SYNC_MODE=remote-sync forces SYNC_ENABLED=true")
            self.sync_enabled = True
        if resolved == "shared-db" and self.sync_remote_base_url:
            self._warn("SYNC_MODE=shared-db ignores SYNC_REMOTE_BASE_URL")
        if resolved == "off" and (self.sync_enabled or self.sync_remote_base_url):
            self._warn("SYNC_MODE=off ignores SYNC_ENABLED/SYNC_REMOTE_BASE_URL")
        return resolved

    def _parse_cors_origins(self) -> list[str]:
        defaults = [
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:18741",
            "http://localhost:18741",
            "tauri://localhost",
        ]
        if (_env_bool("PUBLIC_MODE") or os.getenv("APP_ENV", "").lower() == "production" or self.public_base_url):
            defaults = []
        if self.public_base_url:
            defaults.append(self.public_base_url.rstrip("/"))

        raw = os.getenv("CORS_ORIGINS", "").strip()
        if raw:
            parsed: list[str]
            try:
                if raw.startswith("["):
                    candidate = json.loads(raw)
                    parsed = [self._normalize_origin_value(str(item)) for item in candidate if str(item).strip()]
                else:
                    parsed = [self._normalize_origin_value(item) for item in raw.split(",") if item.strip()]
            except Exception:
                raw_fallback = raw
                if raw_fallback.startswith("[") and raw_fallback.endswith("]"):
                    raw_fallback = raw_fallback[1:-1]
                parsed = [
                    self._normalize_origin_value(item)
                    for item in raw_fallback.split(",")
                    if item.strip()
                ]
            defaults.extend(parsed)

        unique: list[str] = []
        for origin in defaults:
            if origin and origin not in unique:
                unique.append(origin)
        return unique

    @staticmethod
    def _normalize_origin_value(value: str) -> str:
        normalized = value.strip().strip("\"'").strip()
        if normalized.startswith("["):
            normalized = normalized[1:].strip()
        if normalized.endswith("]"):
            normalized = normalized[:-1].strip()
        return normalized

    def _parse_csv_env(self, env_name: str) -> list[str]:
        raw = os.getenv(env_name, "").strip()
        if not raw:
            return []
        return [
            item.strip()
            for item in raw.split(",")
            if item.strip()
        ]

    def runtime_summary(self) -> dict[str, object]:
        return {
            "appEnv": self.app_env,
            "desktopMode": self.desktop_mode,
            "authMode": self.auth_mode,
            "allowDesktopDevFallback": self.allow_desktop_dev_fallback,
            "syncMode": self.sync_mode,
            "syncEnabledFlag": self.sync_enabled,
            "syncWorkerEnabled": self.sync_worker_enabled,
            "syncRemoteConfigured": self.sync_remote_configured,
            "syncPullEnabled": self.sync_pull_enabled,
            "runtimeStatusEnabled": self.runtime_status_enabled,
            "runtimeWorkers": self.runtime_workers,
            "conversionTimeoutSeconds": self.conversion_timeout_seconds,
            "maxFileBytes": self.max_file_bytes,
            "trustedProxyCount": len(self.trusted_proxy_ips),
            "startupWarnings": list(self.startup_warnings),
        }


settings = Settings()
