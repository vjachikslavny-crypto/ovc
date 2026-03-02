from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.agent.draft_types import AgentReply
from app.agent.orchestrator import handle_user_message
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1)
    note_id: Optional[str] = Field(default=None, alias="noteId")

    class Config:
        allow_population_by_field_name = True


class ChatResponse(BaseModel):
    reply: str
    draft: List[dict]


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest, current_user: User = Depends(get_current_user)):
    try:
        agent_reply: AgentReply = handle_user_message(payload.text, payload.note_id)
    except Exception as exc:
        logger.exception("Chat processing error")
        raise HTTPException(status_code=500, detail="Internal chat error") from exc

    return ChatResponse(
        reply=agent_reply.reply,
        draft=[action.dict(by_alias=True) for action in agent_reply.draft],
    )
