from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.prompts import (
    LinkedNote,
    NoteContext,
    RelatedNote,
    build_system_prompt,
    build_user_prompt,
)
from app.agent.token_counter import count_tokens
from app.core.config import settings
from app.db.models import Note, NoteLink, NoteTag
from app.rag.tfidf_index import index as tfidf_index

logger = logging.getLogger(__name__)


def _blocks_to_text(blocks: list[dict]) -> str:
    """Извлекает plain-text из списка блоков.
    
    Блоки с source='ai' пропускаются — AI смотрит только на текст человека.
    """
    lines: list[str] = []
    for block in blocks:
        # Пропускаем блоки, написанные самим ИИ
        if block.get("data", {}).get("source") == "ai":
            continue
        b_type = block.get("type")
        data = block.get("data", {})
        if b_type == "heading":
            lines.append(str(data.get("text", "")))
        elif b_type == "paragraph":
            parts = data.get("parts", [])
            lines.append("".join(p.get("text", "") for p in parts))
        elif b_type in {"bulletList", "numberList"}:
            for item in data.get("items", []):
                lines.append(item.get("text", "") if isinstance(item, dict) else str(item))
        elif b_type == "quote":
            lines.append(str(data.get("text", "")))
        elif b_type == "todo":
            for item in data.get("items", []):
                mark = "[x]" if item.get("done") else "[ ]"
                lines.append(f"{mark} {item.get('text', '')}")
        elif b_type == "table":
            for row in data.get("rows", []):
                if isinstance(row, list):
                    lines.append(" | ".join(str(c) for c in row))
        elif b_type == "link":
            lines.append(data.get("title") or data.get("url", ""))
        elif b_type == "source":
            lines.append(f"{data.get('title', '')} ({data.get('domain', '')})")
        elif b_type == "summary":
            lines.append(data.get("text", ""))
    return "\n".join(line for line in lines if line.strip())


def get_note_context(
    note_id: str, user_id: Optional[str], session: Session
) -> Optional[NoteContext]:
    """Загружает контекст заметки из БД."""
    note = session.get(Note, note_id)
    if not note:
        return None
    if user_id and note.user_id and note.user_id != user_id:
        return None

    blocks = json.loads(note.blocks_json or "[]")
    text_content = _blocks_to_text(blocks)

    tags = [
        row.tag
        for row in session.execute(
            select(NoteTag.tag).where(NoteTag.note_id == note_id)
        ).all()
    ]

    link_titles: list[str] = []
    for link in session.execute(
        select(NoteLink.to_id).where(NoteLink.from_id == note_id)
    ).all():
        linked = session.get(Note, link.to_id)
        if linked:
            link_titles.append(linked.title)

    return NoteContext(
        title=note.title,
        text_content=text_content,
        tags=tags,
        links=link_titles,
        block_count=len(blocks),
    )


def get_linked_notes(
    note_id: str,
    user_id: Optional[str],
    session: Session,
    limit: int = 3,
) -> list[LinkedNote]:
    """Загружает полное содержимое заметок, связанных через NoteLink.

    Отличие от TF-IDF: это явные ссылки пользователя, не автоматический поиск.
    """
    result: list[LinkedNote] = []
    for link_row in session.execute(
        select(NoteLink.to_id).where(NoteLink.from_id == note_id)
    ).all():
        if len(result) >= limit:
            break
        linked_note = session.get(Note, link_row.to_id)
        if not linked_note:
            continue
        if user_id and linked_note.user_id and linked_note.user_id != user_id:
            continue

        blocks = json.loads(linked_note.blocks_json or "[]")
        text = _blocks_to_text(blocks)

        tags = [
            row.tag
            for row in session.execute(
                select(NoteTag.tag).where(NoteTag.note_id == linked_note.id)
            ).all()
        ]

        result.append(LinkedNote(
            title=linked_note.title,
            text_content=text,
            tags=tags,
        ))

    return result


def get_related_notes(
    query: str,
    user_id: Optional[str],
    session: Session,
    limit: int = 5,
    exclude_note_id: Optional[str] = None,
) -> list[RelatedNote]:
    """Ищет похожие заметки через TF-IDF индекс."""
    results = tfidf_index.search(query, limit=limit + 5)
    related: list[RelatedNote] = []
    seen_ids: set[str] = set()

    for hit in results:
        nid = hit["note_id"]
        if nid in seen_ids:
            continue
        if exclude_note_id and nid == exclude_note_id:
            continue
        seen_ids.add(nid)

        note = session.get(Note, nid)
        if not note:
            continue
        if user_id and note.user_id and note.user_id != user_id:
            continue

        snippet = str(hit.get("text", ""))[:200]
        related.append(
            RelatedNote(title=note.title, snippet=snippet, score=float(hit["score"]))
        )
        if len(related) >= limit:
            break

    return related


def assemble_context(
    note_id: Optional[str],
    user_message: str,
    user_id: Optional[str],
    session: Session,
    mode: str = "chat",
) -> tuple[str, str]:
    """Собирает system prompt и user prompt с полным контекстом.

    Returns:
        (system_prompt, user_prompt)
    """
    budget = settings.llm_context_budget
    note_ctx: Optional[NoteContext] = None
    linked: list[LinkedNote] = []
    related: list[RelatedNote] = []

    # 1. Контекст текущей заметки (нужен для всех режимов)
    if note_id:
        note_ctx = get_note_context(note_id, user_id, session)

    # 2. Связанные заметки через NoteLink (для chat/explain)
    if note_id and mode in ("chat", "explain"):
        linked = get_linked_notes(note_id, user_id, session, limit=3)

    # 3. Похожие заметки через TF-IDF (только для chat)
    if mode == "chat":
        search_query = f"{note_ctx.title} {user_message}" if note_ctx else user_message
        related = get_related_notes(
            search_query, user_id, session, limit=5, exclude_note_id=note_id
        )

    # 4. Системный промпт
    system_prompt = build_system_prompt(mode=mode)

    # 5. Токен-бюджет
    used = count_tokens(system_prompt) + count_tokens(user_message)
    context_trimmed = False

    if note_ctx:
        note_cost = count_tokens(note_ctx.text_content) + count_tokens(note_ctx.title)
        if used + note_cost > budget:
            # Обрезаем текст заметки до доступного бюджета
            available = max(budget - used - 100, 200)  # резерв 100 токенов
            # Грубая обрезка: ~4 символа на токен
            max_chars = available * 4
            if len(note_ctx.text_content) > max_chars:
                note_ctx.text_content = note_ctx.text_content[:max_chars] + "\n\n[... текст обрезан из-за ограничения контекста]"
                context_trimmed = True
        used += count_tokens(note_ctx.text_content) + count_tokens(note_ctx.title)

    trimmed_linked: list[LinkedNote] = []
    for n in linked:
        cost = count_tokens(n.title) + count_tokens(n.text_content)
        if used + cost > budget:
            break
        used += cost
        trimmed_linked.append(n)

    trimmed_related: list[RelatedNote] = []
    for r in related:
        cost = count_tokens(r.title) + count_tokens(r.snippet)
        if used + cost > budget:
            break
        used += cost
        trimmed_related.append(r)

    if context_trimmed:
        logger.info("Note context trimmed to fit budget: %d/%d tokens", used, budget)
    else:
        logger.debug("Context budget used: %d/%d tokens", used, budget)

    # 6. User prompt
    user_prompt = build_user_prompt(
        user_message,
        note_ctx,
        trimmed_related or None,
        trimmed_linked or None,
        mode=mode,
    )

    # Если контекст был обрезан — добавляем предупреждение в user_prompt
    if context_trimmed:
        user_prompt += "\n\n⚠️ ВНИМАНИЕ: Текст заметки был обрезан из-за ограничения контекста. Конспект охватывает только часть заметки."

    return system_prompt, user_prompt
