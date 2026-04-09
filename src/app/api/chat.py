from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.draft_types import AgentReply, ChatMessage
from app.agent.orchestrator import handle_user_message, stream_user_message, MODES
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    text: str = Field(default="")
    note_id: Optional[str] = Field(default=None, alias="noteId")

    # Режим работы агента:
    # "chat"      — обычный разговор (по умолчанию)
    # "summarize_text" — Сделать конспект по заметке на основе текста который там уже есть
    # "detailed"  — Сделать конспект большую часть которой написал ИИ, а также объсянение
    # "explain"   — Объяснение
    mode: str = Field(default="chat")

    # История диалога (предыдущие сообщения)
    messages: List[ChatMessage] = Field(default_factory=list)

    class Config:
        allow_population_by_field_name = True


class ChatResponse(BaseModel):
    reply: str
    draft: List[dict] = Field(default_factory=list)
    mode: str = "chat"


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    mode = payload.mode if payload.mode in MODES else "chat"
    try:
        agent_reply: AgentReply = handle_user_message(
            payload.text,
            note_id=payload.note_id,
            user_id=current_user.id,
            mode=mode,
            messages=payload.messages or None,
        )
    except Exception as exc:
        logger.exception("Chat processing error")
        raise HTTPException(status_code=500, detail="Internal chat error") from exc

    return ChatResponse(
        reply=agent_reply.reply,
        draft=[a.dict(by_alias=True) for a in agent_reply.draft],
        mode=agent_reply.mode,
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """SSE-стриминг ответа агента (все режимы)."""
    mode = payload.mode if payload.mode in MODES else "chat"

    async def generate() -> AsyncGenerator[str, None]:
        try:
            for event in stream_user_message(
                payload.text,
                note_id=payload.note_id,
                user_id=current_user.id,
                mode=mode,
                messages=payload.messages or None,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.exception("Stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Ошибка стриминга'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
