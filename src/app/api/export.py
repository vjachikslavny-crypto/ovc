from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from app.db.models import Note
from app.db.session import get_session
from app.core.ownership import get_owned_note
from app.core.security import get_current_user_or_refresh
from app.models.user import User

router = APIRouter(tags=["export"])


@router.get("/export/docx/{note_id}")
def export_docx_stub(note_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    with get_session() as session:
        get_owned_note(session, note_id, current_user.id)

    # TODO: implement real DOCX generation using python-docx or a similar library.
    return {
        "status": "todo",
        "detail": "DOCX export is not implemented yet. Convert HTML/blocks to a .docx file here.",
    }
