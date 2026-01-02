from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        self.database_url = (
            os.getenv("DATABASE_URL")
            or os.getenv("SIMPLE_DB_URL")
            or "sqlite:///./simple_app/ovc.db"
        )
        self.secret_key = os.getenv(
            "SECRET_KEY", "CHANGE_ME_CHANGE_ME_CHANGE_ME_CHANGE_ME"
        )
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY должен быть не короче 32 символов.")
        self.access_token_expires_min = int(os.getenv("ACCESS_TOKEN_EXPIRES_MIN", "15"))
        self.refresh_token_expires_days = int(os.getenv("REFRESH_TOKEN_EXPIRES_DAYS", "30"))
        self.cookie_domain = os.getenv("COOKIE_DOMAIN") or None
        self.cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
        self.cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax")
        self.rate_limit_window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.rate_limit_max = int(os.getenv("RATE_LIMIT_MAX", "60"))
        self.password_min_length = int(os.getenv("PASSWORD_MIN_LENGTH", "6"))
        self.password_require_upper = os.getenv("PASSWORD_REQUIRE_UPPER", "false").lower() == "true"
        self.password_require_lower = os.getenv("PASSWORD_REQUIRE_LOWER", "false").lower() == "true"
        self.password_require_digit = os.getenv("PASSWORD_REQUIRE_DIGIT", "false").lower() == "true"
        self.password_require_symbol = os.getenv("PASSWORD_REQUIRE_SYMBOL", "false").lower() == "true"
        self.email_from = os.getenv("EMAIL_FROM", "no-reply@ovc.local")
        self.email_backend = os.getenv("EMAIL_BACKEND", "mock")


settings = Settings()
