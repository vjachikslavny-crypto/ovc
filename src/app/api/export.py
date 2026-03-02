from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from app.db.models import Note
from app.db.session import get_session
from app.core.security import get_current_user_or_refresh
from app.models.user import User

router = APIRouter(tags=["export"])


@router.get("/export/docx/{note_id}")
async def export_docx_stub(note_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        if note.user_id is None:
            note.user_id = current_user.id
            session.add(note)
            session.flush()
        if note.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Note not found")

    # TODO: implement real DOCX generation using python-docx or a similar library.
    return {
        "status": "todo",
        "detail": "DOCX export is not implemented yet. Convert HTML/blocks to a .docx file here.",
    }
