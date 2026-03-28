from __future__ import annotations

import re
from typing import List

from app.core.config import settings

_SYMBOL_RE = re.compile(r"[^A-Za-z0-9]")
_COMMON_PASSWORDS = {
    "12345678",
    "123456789",
    "1234567890",
    "qwerty123",
    "password",
    "password123",
    "admin123",
    "letmein",
    "welcome123",
    "iloveyou",
}


def validate_password(password: str) -> List[str]:
    errors: List[str] = []
    if len(password) < settings.password_min_length:
        errors.append(f"Пароль должен содержать минимум {settings.password_min_length} символов.")

    has_upper = any(char.isupper() for char in password)
    has_lower = any(char.islower() for char in password)
    has_digit = any(char.isdigit() for char in password)
    has_symbol = bool(_SYMBOL_RE.search(password))

    class_checks = {
        "верхний регистр": has_upper,
        "нижний регистр": has_lower,
        "цифру": has_digit,
        "символ": has_symbol,
    }
    class_count = sum(class_checks.values())

    if class_count < settings.password_min_character_classes:
        errors.append(
            f"Пароль должен содержать минимум {settings.password_min_character_classes} "
            "типа символов: верхний/нижний регистр, цифры, символы."
        )

    required_flags = {
        "верхний регистр": settings.password_require_upper,
        "нижний регистр": settings.password_require_lower,
        "цифру": settings.password_require_digit,
        "символ": settings.password_require_symbol,
    }
    for label, required in required_flags.items():
        if required and not class_checks[label]:
            errors.append(f"Пароль должен содержать {label}.")

    if password.lower() in _COMMON_PASSWORDS:
        errors.append("Пароль слишком простой. Используйте более сложную комбинацию.")

    return errors


def password_policy_hint() -> str:
    return (
        f"Минимум {settings.password_min_length} символов и минимум "
        f"{settings.password_min_character_classes} из 4 классов: "
        "верхний/нижний регистр, цифры, символы."
    )
