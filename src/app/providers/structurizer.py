from __future__ import annotations

from typing import Any, Dict, List

from app.agent.draft_types import DraftAction
from app.providers.llm_provider import LLMProvider


def to_draft_actions(raw_input: Dict[str, Any], schema: Dict[str, Any], llm: LLMProvider) -> List[DraftAction]:
    """Преобразует сырой ввод в DraftAction.

    Пока возвращает пустой список (безопасный режим). В дальнейшем сюда
    подключим вызовы моделей через LLMProvider.
    """

    _ = (raw_input, schema, llm)  # placeholders
    return []
