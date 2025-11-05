from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.draft_types import AgentReply
from app.agent.orchestrator import handle_user_message
from app.log import dataset_logger

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
async def chat_endpoint(payload: ChatRequest):
    try:
        agent_reply: AgentReply = handle_user_message(payload.text, payload.note_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    dataset_logger.append(
        {
            "kind": "chat",
            "input": payload.text,
            "noteId": payload.note_id,
            "draft": [action.dict(by_alias=True) for action in agent_reply.draft],
        }
    )

    return ChatResponse(
        reply=agent_reply.reply,
        draft=[action.dict(by_alias=True) for action in agent_reply.draft],
    )
