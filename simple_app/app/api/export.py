from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.db.models import Note
from app.db.session import get_session
from app.log import dataset_logger

router = APIRouter(tags=["export"])


@router.get("/dataset/export", response_class=PlainTextResponse)
async def export_dataset(from_ts: Optional[str] = None, to_ts: Optional[str] = None) -> PlainTextResponse:
    payload = dataset_logger.export(from_ts=from_ts, to_ts=to_ts)
    return PlainTextResponse(content=payload or "", media_type="text/plain")


@router.get("/export/docx/{note_id}")
async def export_docx_stub(note_id: str):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")

    # TODO: implement real DOCX generation using python-docx or a similar library.
    return {
        "status": "todo",
        "detail": "DOCX export is not implemented yet. Convert HTML/blocks to a .docx file here.",
    }
