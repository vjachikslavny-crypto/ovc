import hashlib
from typing import Optional


def chat(prompt: str, system_prompt: Optional[str] = None) -> str:
    seed = f"{system_prompt or ''}::{prompt}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()[:8]
    return f"Mock reply ({digest}): предложения сохранены локально."
