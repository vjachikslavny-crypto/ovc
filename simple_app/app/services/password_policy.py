from __future__ import annotations

from typing import List

from app.core.config import settings


def validate_password(password: str) -> List[str]:
    errors: List[str] = []
    if len(password) < settings.password_min_length:
        errors.append(f"Пароль должен быть длиннее {settings.password_min_length - 1} символов.")

    return errors
