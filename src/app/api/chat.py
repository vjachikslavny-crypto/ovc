from __future__ import annotations

import json
import asyncio
import queue
import threading
import logging
from typing import AsyncGenerator, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.draft_types import AgentReply, ChatMessage
from app.agent.orchestrator import handle_user_message, stream_user_message, MODES
from app.core.security import get_current_user
from app.models.user import User
from app.core.config import settings
from app.services.runtime import run_blocking, run_for_request, check_cancelled
from app.services.rate_limit import limit_operation

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    text: str = Field(default="", max_length=100000)
    note_id: Optional[str] = Field(default=None, alias="noteId")

    # Режим работы агента:
    # "chat"      — обычный разговор (по умолчанию)
    # "summarize_text" — Сделать конспект по заметке на основе текста который там уже есть
    # "detailed"  — Сделать конспект большую часть которой написал ИИ, а также объсянение
    # "explain"   — Объяснение
    mode: str = Field(default="chat")

    # История диалога (предыдущие сообщения)
    messages: List[ChatMessage] = Field(default_factory=list, max_length=100)

    class Config:
        allow_population_by_field_name = True


class ChatResponse(BaseModel):
    reply: str
    draft: List[dict] = Field(default_factory=list)
    mode: str = "chat"


def _validate_runtime(payload, user):
    limit_operation('ai', user.id, settings.rate_limit_ai_per_min)
    if len(payload.text) + sum(len(m.text) for m in payload.messages) > settings.max_ai_context_chars:
        raise HTTPException(413, 'AI input exceeds the configured context limit')


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    _validate_runtime(payload, current_user)
    mode = payload.mode if payload.mode in MODES else "chat"
    try:
        agent_reply: AgentReply = await run_for_request(request, handle_user_message,
            payload.text,
            raise_errors=True,
            note_id=payload.note_id,
            user_id=current_user.id,
            mode=mode,
            messages=payload.messages or None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("chat_failed type=%s", type(exc).__name__)
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
    _validate_runtime(payload, current_user)
    mode = payload.mode if payload.mode in MODES else "chat"

    async def generate() -> AsyncGenerator[str, None]:
        events = queue.Queue(maxsize=8)
        stopped = threading.Event()
        def produce():
            iterator = stream_user_message(payload.text, note_id=payload.note_id,
                user_id=current_user.id, mode=mode, messages=payload.messages or None)
            try:
                for event in iterator:
                    check_cancelled()
                    while not stopped.is_set():
                        try:
                            events.put(event, timeout=.1)
                            break
                        except queue.Full:
                            check_cancelled()
                    if stopped.is_set():
                        break
            finally:
                iterator.close()
        task = asyncio.create_task(run_blocking(produce, timeout=settings.llm_timeout_seconds + 5))
        try:
            while not task.done() or not events.empty():
                try:
                    event = events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(.02)
                    continue
                yield f"data: {json.dumps(event)}\n\n"
            await task
        except HTTPException as exc:
            yield f"data: {json.dumps({'type':'error', 'message':exc.detail, 'status':exc.status_code})}\n\n"
        except Exception as exc:
            logger.warning('ai_stream_failed type=%s', type(exc).__name__)
            yield f"data: {json.dumps({'type':'error', 'message':'AI stream failed', 'status':502})}\n\n"
        finally:
            stopped.set()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
