from __future__ import annotations

import datetime as dt
import re
from typing import List, Optional

from sqlalchemy import select

from app.agent.draft_types import (
    AgentReply,
    CreateNoteAction,
    DraftAction,
    UpdateNoteAction,
)
from app.db.models import Note
from app.db.session import get_session
from app.providers import llm_mock
from app.rag.chunking import chunk_markdown
from app.rag.tfidf_index import index

COMMAND_CREATE = re.compile(r"\b(создай|создать|сделай|create)\b", re.IGNORECASE)
COMMAND_UPDATE = re.compile(r"\b(обнови|дополни|расширь|summary|сводка)\b", re.IGNORECASE)


def handle_user_message(text: str, note_id: Optional[str] = None) -> AgentReply:
    note_refs = _load_notes()
    draft: List[DraftAction] = []
    lower = text.lower()

    target_note = next((note for note in note_refs if note["id"] == note_id), None)

    if target_note and COMMAND_UPDATE.search(lower):
        draft.append(_build_update_action(target_note["id"], text))
    elif note_id:
        draft.append(_build_update_action(note_id, text))
    else:
        draft.append(_build_create_action(text))

    related = index.search(text, limit=3)
    reply = _build_reply(text, draft, related)
    return AgentReply(reply=reply, draft=draft)


def _load_notes() -> List[dict]:
    with get_session() as session:
        records = session.execute(select(Note)).scalars().all()

    for note in records:
        chunks = chunk_markdown(note.content_md)
        index.upsert(note.id, [(f"{note.id}:{idx}", text) for idx, text in enumerate(chunks)])

    return [{"id": note.id, "title": note.title, "content_md": note.content_md} for note in records]


def _build_create_action(message: str) -> CreateNoteAction:
    title = _derive_title(message)
    body = f"# {title}\n\n- {message.strip()}"
    return CreateNoteAction(title=title, content_md=body)


def _build_update_action(note_id: str, message: str) -> UpdateNoteAction:
    today = dt.date.today().isoformat()
    patch = f"## Сводка ({today})\n- {message.strip()}"
    return UpdateNoteAction(id=note_id, patch_md=patch, position="append")


def _derive_title(message: str) -> str:
    first_line = message.strip().splitlines()[0]
    cleaned = re.sub(r"[^\w\s-]", "", first_line).strip()
    return cleaned[:80] or "Новая заметка"


def _build_reply(message: str, draft: List[DraftAction], related: List[dict]) -> str:
    summary_lines = []
    for action in draft:
        if isinstance(action, CreateNoteAction):
            summary_lines.append(f"Создать «{action.title}»." )
        elif isinstance(action, UpdateNoteAction):
            summary_lines.append(f"Обновить заметку {action.id}.")
        else:
            summary_lines.append(f"Действие {action.type}.")

    if related:
        similar_ids = sorted({item["note_id"] for item in related})
        summary_lines.append(
            "Похожие заметки: " + ", ".join(similar_ids)
        )

    prompt = (
        "Пользователь написал: "
        + message
        + "\nПредложенные шаги: "
        + " ".join(summary_lines)
    )
    reply = llm_mock.chat(prompt, "Ты локальный ассистент, отвечай кратко и дружелюбно.")
    return reply
