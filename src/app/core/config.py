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
        self.cookie_secure = _env_bool("COOKIE_SECURE", False)
        self.cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax")
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

        self.csp_report_only = _env_bool("CSP_REPORT_ONLY", False)
        self.csp_script_src_extra = self._parse_csv_env("CSP_SCRIPT_SRC_EXTRA")
        self.csp_style_src_extra = self._parse_csv_env("CSP_STYLE_SRC_EXTRA")
        self.csp_connect_src_extra = self._parse_csv_env("CSP_CONNECT_SRC_EXTRA")
        self.csp_img_src_extra = self._parse_csv_env("CSP_IMG_SRC_EXTRA")
        self.csp_frame_src_extra = self._parse_csv_env("CSP_FRAME_SRC_EXTRA")

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
            "startupWarnings": list(self.startup_warnings),
        }


settings = Settings()
