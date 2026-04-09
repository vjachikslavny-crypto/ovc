from __future__ import annotations

import json
import logging
import re
from typing import Generator, Optional

from pydantic import TypeAdapter

from app.agent.draft_types import AgentReply, ChatMessage, DraftAction
from app.agent.context import assemble_context
from app.db.session import get_session
from app.providers.llm_provider import MockLLM, get_llm

logger = logging.getLogger(__name__)

# Все допустимые режимы
MODES = {"chat", "summarize_text", "detailed", "explain"}


def _history_to_gemini(messages: list[ChatMessage]) -> list[dict]:
    """Конвертирует историю ChatMessage -> формат Gemini multi-turn."""
    result = []
    for msg in messages:
        role = "model" if msg.role == "assistant" else "user"
        result.append({"role": role, "parts": [{"text": msg.text}]})
    return result


def _log_dialog(user_id: Optional[str], note_id: Optional[str], mode: str,
                user_text: str, assistant_text: str) -> None:
    """Записывает сообщения пользователя и ассистента в MessageLog."""
    try:
        from app.db.models import MessageLog
        with get_session() as session:
            session.add(MessageLog(
                role="user",
                text=user_text,
                user_id=user_id,
                note_id=note_id,
                mode=mode,
            ))
            session.add(MessageLog(
                role="assistant",
                text=assistant_text,
                user_id=user_id,
                note_id=note_id,
                mode=mode,
            ))
    except Exception as exc:
        logger.warning("Dialog logging failed: %s", exc)


def _parse_llm_response(raw: str) -> tuple[str, list[DraftAction]]:
    """Извлекает reply и draft actions из JSON ответа."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        # Пытаемся найти первый { просто как fallback
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end+1]

    try:
        data = json.loads(raw, strict=False)
        reply = data.get("reply", "")
        # Если reply пустой, пробуем вернуть исходный текст, если мы не смогли вообще ничего спарсить.
        draft_raw = data.get("draft", [])

        if not isinstance(draft_raw, list):
            draft_raw = []

        actions = []
        ta = TypeAdapter(DraftAction)
        for item in draft_raw:
            try:
                # В Pydantic v2 TypeAdapter корректно резолвит Union
                # Авто-нормализация для блоков без "data"
                if item.get("type") == "insert_block" and "block" in item:
                    b_type = item["block"].get("type")
                    if b_type and "data" not in item["block"]:
                        # переносим все ключи кроме type в data
                        data_fields = {k: v for k, v in item["block"].items() if k != "type" and k != "noteId" and k != "afterId"}
                        item["block"] = {"type": b_type, "data": data_fields}

                act = ta.validate_python(item)
                actions.append(act)
            except Exception as e:
                logger.warning("Draft action validation failed: %s", e)

        return reply, actions
        
    except Exception as e:
        logger.warning("_parse_llm_response JSON error: %s", e)
        # Если это не JSON, возвращаем исходный текст
        return raw.strip(), []


def _consolidate_drafts(draft_actions: list[DraftAction]) -> list[DraftAction]:
    """Объединяет все insert_block actions в один paragraph (anti-fragmentation)."""
    insert_actions = [a for a in draft_actions if a.type == "insert_block"]
    if not insert_actions:
        return draft_actions

    from app.agent.draft_types import InsertBlockAction, BlockPayload

    all_text_parts = []
    for act in insert_actions:
        b = act.block
        if b.type == "heading":
            all_text_parts.append(b.data.get('text', '').upper())
        elif b.type in ("bulletList", "numberList"):
            items = b.data.get("items", [])
            list_text = "\n".join(
                f"- {item.get('text', '') if isinstance(item, dict) else item}"
                for item in items
            )
            all_text_parts.append(list_text)
        elif b.type == "paragraph":
            p_text = "".join(
                part.get("text", "") for part in b.data.get("parts", [])
            )
            if p_text:
                all_text_parts.append(p_text)
        elif b.type == "quote":
            all_text_parts.append(b.data.get('text', ''))
        elif b.data.get("text"):
            all_text_parts.append(b.data.get("text"))

    final_text = "\n\n".join(all_text_parts)
    if not final_text:
        return draft_actions

    new_block = BlockPayload(
        type="paragraph",
        data={"parts": [{"text": final_text}]}
    )
    main_action = InsertBlockAction(
        type="insert_block",
        note_id=insert_actions[0].note_id,
        after_id=insert_actions[0].after_id,
        block=new_block,
    )
    other_actions = [a for a in draft_actions if a.type != "insert_block"]
    return [main_action] + other_actions


def handle_user_message(
    text: str,
    note_id: Optional[str] = None,
    user_id: Optional[str] = None,
    mode: str = "chat",
    messages: Optional[list[ChatMessage]] = None,
) -> AgentReply:
    """Обрабатывает сообщение пользователя через LLM.

    Все режимы возвращают текстовый ответ (без draft actions).

    Args:
        text: Текст сообщения пользователя.
        note_id: ID текущей заметки (опционально).
        user_id: ID пользователя (опционально).
        mode: "chat" | "summarize" | "detailed" | "explain"
        messages: История диалога (предыдущие сообщения).
    """
    if mode not in MODES:
        mode = "chat"

    llm = get_llm()

    if isinstance(llm, MockLLM):
        reply = _stub_reply(mode)
        _log_dialog(user_id, note_id, mode, text, reply.reply)
        return reply

    try:
        with get_session() as session:
            system_prompt, user_prompt = assemble_context(
                note_id, text, user_id, session, mode=mode,
            )

        # Если есть история — используем multi-turn API
        if messages:
            gemini_history = _history_to_gemini(messages)
            raw_response = llm.chat_with_history(system_prompt, gemini_history, user_prompt)
        else:
            raw_response = llm.chat(system_prompt, user_prompt)

        reply_text, draft_actions = _parse_llm_response(raw_response)
        
        # Для режимов общения (chat) и объяснения (explain) принудительно очищаем draft,
        # чтобы ИИ отвечал только в чат и не внедрял текст в саму заметку.
        if mode in ("chat", "explain"):
            draft_actions = []
        else:
            # Anti-fragmentation: объединяем все insert_block в один paragraph
            draft_actions = _consolidate_drafts(draft_actions)
        
        # Автоматическая простановка note_id, если LLM не заполнил
        if note_id:
            for action in draft_actions:
                if getattr(action, "note_id", None) is None:
                    action.note_id = note_id

        result = AgentReply(reply=reply_text, draft=draft_actions, mode=mode)
        _log_dialog(user_id, note_id, mode, text, reply_text)
        return result

    except Exception as exc:
        logger.exception("LLM call failed: %s", exc)
        return AgentReply(
            reply="Не удалось связаться с AI. Попробуйте позже.",
            draft=[], mode=mode,
        )


def stream_user_message(
    text: str,
    note_id: Optional[str] = None,
    user_id: Optional[str] = None,
    mode: str = "chat",
    messages: Optional[list[ChatMessage]] = None,
) -> Generator[dict, None, None]:
    """Стриминг ответа агента для ВСЕХ режимов.

    Yields: dict-события:
      {"type": "delta", "text": "..."} — чанк текста (chat/explain)
      {"type": "reply", "text": "..."} — полный reply (summarize/detailed)
      {"type": "draft", "draft": [...]} — draft actions (summarize/detailed)
      {"type": "error", "message": "..."} — ошибка
      {"type": "done"} — конец стрима
    """
    if mode not in MODES:
        mode = "chat"

    llm = get_llm()

    if isinstance(llm, MockLLM):
        yield {"type": "delta", "text": "MOCK: нет подключения к AI"}
        yield {"type": "done"}
        return

    try:
        stream_mode = "stream" if mode in ("chat", "explain") else mode
        with get_session() as session:
            system_prompt, user_prompt = assemble_context(
                note_id, text, user_id, session, mode=stream_mode if stream_mode == "stream" else mode,
            )

        gemini_history = _history_to_gemini(messages) if messages else None
        use_json = mode in ("summarize_text", "detailed")

        full_chunks: list[str] = []
        for chunk in llm.stream_chat(system_prompt, user_prompt, history=gemini_history, json_mode=use_json):
            full_chunks.append(chunk)
            # Для chat/explain — стримим текст по мере поступления
            if not use_json:
                yield {"type": "delta", "text": chunk}

        complete = "".join(full_chunks)

        if use_json:
            # Парсим JSON-ответ, применяем anti-fragmentation
            reply_text, draft_actions = _parse_llm_response(complete)

            # Anti-fragmentation для summarize/detailed
            draft_actions = _consolidate_drafts(draft_actions)

            # Автопростановка note_id
            if note_id:
                for action in draft_actions:
                    if getattr(action, "note_id", None) is None:
                        action.note_id = note_id

            yield {"type": "reply", "text": reply_text}
            if draft_actions:
                yield {"type": "draft", "draft": [a.dict(by_alias=True) for a in draft_actions]}

        _log_dialog(user_id, note_id, mode, text, complete if not use_json else reply_text)

    except Exception as exc:
        logger.exception("Stream LLM call failed: %s", exc)
        yield {"type": "error", "message": "Не удалось связаться с AI. Попробуйте позже."}

    yield {"type": "done"}


def _stub_reply(mode: str = "chat") -> AgentReply:
    """Заглушка при отсутствии LLM."""
    stubs = {
        "summarize": "Конспект временно недоступен — нет подключения к AI.",
        "detailed": "Подробный конспект временно недоступен — нет подключения к AI.",
        "explain": "Объяснение временно недоступно — нет подключения к AI.",
    }
    reply = stubs.get(mode, "Нет подключения к AI. Установите GEMINI_API_KEY.")
    return AgentReply(reply=reply, draft=[], mode=mode)
