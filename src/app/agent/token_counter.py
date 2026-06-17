from __future__ import annotations

import re

_tiktoken_enc = None

# Llama-3 использует кастомный BPE (128k vocab), не совпадающий с GPT-4.
# tiktoken cl100k_base занижает счёт для кириллицы (~15-20%).
# Коэффициент коррекции компенсирует разницу токенизаторов.
_LLAMA_CORRECTION = 1.15


def _get_tiktoken():
    global _tiktoken_enc
    if _tiktoken_enc is None:
        try:
            import tiktoken
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_enc = False  # отмечаем что попытка была
    return _tiktoken_enc if _tiktoken_enc else None


def count_tokens(text: str) -> int:
    """Подсчёт токенов с коррекцией под Llama-3.

    Приоритет:
    1. tiktoken cl100k_base × коэффициент коррекции
    2. Word-based heuristic (лучше чем len//4, особенно для русского)
    """
    enc = _get_tiktoken()
    if enc is not None:
        try:
            raw = len(enc.encode(text))
            return int(raw * _LLAMA_CORRECTION)
        except Exception:
            pass
    # Fallback: каждое слово/пунктуация ≈ 1 токен
    return len(re.findall(r'\w+|[^\w\s]', text))
