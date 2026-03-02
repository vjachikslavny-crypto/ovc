from __future__ import annotations

import json
import logging
import uuid
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agent.draft_types import (
    AddLinkAction,
    AddTagAction,
    RemoveTagAction,
    DraftAction,
    InsertBlockAction,
    MoveBlockAction,
    SetStyleAction,
    UpdateBlockAction,
)
from app.db.models import Note, NoteLink, NoteTag
from app.db.session import get_session
from app.api.notes import _reindex_note
from app.utils.layout_hints import dumps_layout_hints, merge_layout_hints
from app.core.security import get_current_user
from app.models.user import User
from app.services.audit import log_event
from app.services.sync_engine import OP_COMMIT, enqueue_sync_operation

router = APIRouter(tags=["commit"])


class CommitRequest(BaseModel):
    draft: List[DraftAction] = Field(default_factory=list)


class CommitResponse(BaseModel):
    applied: int
    notes_changed: List[str]


@router.post("/commit", response_model=CommitResponse)
async def commit_endpoint(
    payload: CommitRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    if not payload.draft:
        raise HTTPException(status_code=400, detail="Draft is empty")

    applied = 0
    notes_requiring_index: Set[str] = set()
    touched_notes: Set[str] = set()

    with get_session() as session:
        try:
            for action in payload.draft:
                if isinstance(action, InsertBlockAction):
                    note = _require_note(session, action.note_id, current_user)
                    blocks = json.loads(note.blocks_json or "[]")
                    block_dict = action.block.dict(by_alias=True)
                    if not block_dict.get("id"):
                        block_dict["id"] = str(uuid.uuid4())
                    blocks = _insert_block(blocks, block_dict, action.after_id)
                    note.blocks_json = json.dumps(blocks, ensure_ascii=False)
                    session.add(note)
                    touched_notes.add(note.id)
                    notes_requiring_index.add(note.id)
                    applied += 1

                elif isinstance(action, UpdateBlockAction):
                    note = _require_note(session, action.note_id, current_user)
                    blocks = json.loads(note.blocks_json or "[]")
                    if _patch_block(blocks, action.block_id, action.patch):
                        note.blocks_json = json.dumps(blocks, ensure_ascii=False)
                        session.add(note)
                        touched_notes.add(note.id)
                        notes_requiring_index.add(note.id)
                        applied += 1

                elif isinstance(action, MoveBlockAction):
                    note = _require_note(session, action.note_id, current_user)
                    blocks = json.loads(note.blocks_json or "[]")
                    if _move_block(blocks, action.block_id, action.after_id):
                        note.blocks_json = json.dumps(blocks, ensure_ascii=False)
                        session.add(note)
                        touched_notes.add(note.id)
                        notes_requiring_index.add(note.id)
                        applied += 1

                elif isinstance(action, AddTagAction):
                    note = _require_note(session, action.note_id, current_user)
                    exists = (
                        session.execute(
                            select(NoteTag).where(
                                NoteTag.note_id == note.id,
                                NoteTag.tag == action.tag,
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if not exists:
                        session.add(NoteTag(note_id=note.id, tag=action.tag))
                        touched_notes.add(note.id)
                        applied += 1

                elif isinstance(action, RemoveTagAction):
                    note = _require_note(session, action.note_id, current_user)
                    tag_to_remove = (
                        session.execute(
                            select(NoteTag).where(
                                NoteTag.note_id == note.id,
                                NoteTag.tag == action.tag,
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if tag_to_remove:
                        session.delete(tag_to_remove)
                        touched_notes.add(note.id)
                        applied += 1

                elif isinstance(action, AddLinkAction):
                    source = _require_note(session, action.from_id, current_user)
                    target = _require_note(session, action.to_id, current_user)
                    existing = (
                        session.execute(
                            select(NoteLink).where(
                                NoteLink.from_id == source.id,
                                NoteLink.to_id == target.id,
                                NoteLink.reason == action.reason,
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if not existing:
                        session.add(
                            NoteLink(
                                from_id=source.id,
                                to_id=target.id,
                                reason=action.reason,
                                confidence=action.confidence,
                            )
                        )
                        touched_notes.add(source.id)
                        applied += 1

                elif isinstance(action, SetStyleAction):
                    note = _require_note(session, action.note_id, current_user)
                    note.style_theme = action.style_theme
                    if action.layout_hints is not None:
                        merged_hints = merge_layout_hints(note.layout_hints, action.layout_hints)
                        note.layout_hints = dumps_layout_hints(merged_hints)
                    session.add(note)
                    touched_notes.add(note.id)
                    applied += 1

        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Commit processing error")
            raise HTTPException(status_code=500, detail="Internal commit error") from exc

        for note_id in notes_requiring_index:
            note = session.get(Note, note_id)
            if note:
                _reindex_note(session, note)

        session.flush()

        for note_id in touched_notes:
            log_event(session, "NOTE_UPDATE", user_id=current_user.id, request=request, metadata={"note_id": note_id})

        enqueue_sync_operation(
            session,
            OP_COMMIT,
            {"draft": [action.dict(by_alias=True) for action in payload.draft]},
            user_id=current_user.id,
        )

    return CommitResponse(applied=applied, notes_changed=list(touched_notes))


def _require_note(session, note_id: Optional[str], user: User) -> Note:
    if not note_id:
        raise HTTPException(status_code=400, detail="Draft action missing noteId")
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    if note.user_id is None:
        note.user_id = user.id
        session.add(note)
        session.flush()
    if note.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return note


def _insert_block(blocks: List[dict], block: dict, after_id: Optional[str]) -> List[dict]:
    if not blocks or after_id is None:
        return blocks + [block]
    for idx, existing in enumerate(blocks):
        if existing.get("id") == after_id:
            blocks.insert(idx + 1, block)
            return blocks
    blocks.append(block)
    return blocks


def _patch_block(blocks: List[dict], block_id: str, patch: dict) -> bool:
    for existing in blocks:
        if existing.get("id") == block_id:
            existing.update(patch)
            return True
    return False


def _move_block(blocks: List[dict], block_id: str, after_id: Optional[str]) -> bool:
    current_index = next((idx for idx, blk in enumerate(blocks) if blk.get("id") == block_id), None)
    if current_index is None:
        return False
    block = blocks.pop(current_index)
    if after_id is None:
        blocks.insert(0, block)
        return True
    for idx, existing in enumerate(blocks):
        if existing.get("id") == after_id:
            blocks.insert(idx + 1, block)
            return True
    blocks.append(block)
    return True
