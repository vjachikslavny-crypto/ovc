from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.draft_types import AgentReply
from app.agent.orchestrator import handle_user_message
from app.log import dataset_logger

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1)
    noteId: str | None = None


class ChatResponse(BaseModel):
    reply: str
    draft: list[dict]


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    try:
        agent_reply: AgentReply = handle_user_message(payload.text, payload.noteId)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    dataset_logger.append({
        "kind": "chat",
        "input": payload.text,
        "noteId": payload.noteId,
        "draft": [action.dict() for action in agent_reply.draft],
    })

    return ChatResponse(reply=agent_reply.reply, draft=[action.dict() for action in agent_reply.draft])


@router.get("/dataset/export")
async def export_dataset(from_ts: str | None = None, to_ts: str | None = None):
    data = dataset_logger.export(from_ts=from_ts, to_ts=to_ts)
    return {
        "entries": data.splitlines() if data else []
    }
