from __future__ import annotations

from typing import Optional

from app.agent.draft_types import AgentReply


def handle_user_message(text: str, note_id: Optional[str] = None) -> AgentReply:
    """Current orchestrator is a stub: it replies warmly and proposes no actions.

    The interface stays compatible with future GPT integrations that will
    populate DraftAction lists based on structured analysis of the input.
    """

    preview = text.strip()
    if len(preview) > 140:
        preview = preview[:137] + "…"

    reply = "Я сохранил твою мысль. Когда будешь готов – нажми ＋, чтобы оформить её блоками."  # noqa: E501
    if note_id:
        reply = (
            "Заметка обновлена в памяти. Можешь оформить её в редакторе или попросить меня предложить блоки."  # noqa: E501
        )

    return AgentReply(reply=reply, draft=[])
