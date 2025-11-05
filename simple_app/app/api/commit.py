from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agent.draft_types import (
    AddLinkAction,
    AddSourceAction,
    AddTagAction,
    CreateNoteAction,
    DraftAction,
    UpdateNoteAction,
)
from app.db.models import Note, NoteLink, NoteSource, NoteTag, Source
from app.db.session import get_session
from app.log import dataset_logger
from app.rag.chunking import chunk_markdown
from app.rag.tfidf_index import index

router = APIRouter(tags=["commit"])


class CommitRequest(BaseModel):
    draft: List[DraftAction] = Field(..., min_items=1)


class CommitResponse(BaseModel):
    applied: int
    notes_changed: List[str]


@router.post("/commit", response_model=CommitResponse)
async def commit_endpoint(payload: CommitRequest):
    applied = 0
    changed_notes: set[str] = set()

    with get_session() as session:
        try:
            for action in payload.draft:
                if isinstance(action, CreateNoteAction):
                    note = Note(title=action.title, content_md=action.content_md)
                    session.add(note)
                    session.flush()
                    _reindex_note(session, note)
                    changed_notes.add(note.id)
                    applied += 1
                elif isinstance(action, UpdateNoteAction):
                    note = session.get(Note, action.id)
                    if not note:
                        continue
                    if action.position == "append":
                        note.content_md = f"{note.content_md}\n\n{action.patch_md}".strip()
                    else:
                        note.content_md = f"{action.patch_md}\n\n{note.content_md}".strip()
                    session.add(note)
                    session.flush()
                    _reindex_note(session, note)
                    changed_notes.add(note.id)
                    applied += 1
                elif isinstance(action, AddTagAction):
                    tag = NoteTag(note_id=action.note_id, tag=action.tag, weight=action.weight or 1.0)
                    session.add(tag)
                    changed_notes.add(action.note_id)
                    applied += 1
                elif isinstance(action, AddLinkAction):
                    target = session.execute(select(Note).where(Note.title.ilike(action.to_title))).scalar_one_or_none()
                    if not target:
                        continue
                    link = NoteLink(
                        from_id=action.from_id,
                        to_id=target.id,
                        reason=action.reason,
                        confidence=action.confidence,
                    )
                    session.add(link)
                    applied += 1
                elif isinstance(action, AddSourceAction):
                    source = session.execute(select(Source).where(Source.url == action.source.url)).scalar_one_or_none()
                    if not source:
                        source = Source(
                            url=str(action.source.url),
                            domain=action.source.domain,
                            title=action.source.title,
                            summary=action.source.summary,
                            published_at=action.source.published_at,
                        )
                        session.add(source)
                        session.flush()
                    note_source = NoteSource(note_id=action.note_id, source_id=source.id, relevance=1.0)
                    session.add(note_source)
                    changed_notes.add(action.note_id)
                    applied += 1
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    dataset_logger.append({
        "kind": "commit",
        "draft": [action.dict() for action in payload.draft],
        "applied": applied,
        "rejected": len(payload.draft) - applied,
        "notes_changed": list(changed_notes),
    })

    return CommitResponse(applied=applied, notes_changed=list(changed_notes))


def _reindex_note(session, note: Note) -> None:
    tags = [tag.tag for tag in note.tags]
    meta_chunk = (
        f"{note.id}:meta",
        f"{note.title}\nTags: {', '.join(tags)}\nPriority: {note.priority}\nStatus: {note.status}\n"
        f"Cluster: {note.cluster}\nImportance: {note.importance}"
    )
    content_chunks = chunk_markdown(note.content_md)
    combined = [(f"{note.id}:{idx}", text) for idx, text in enumerate(content_chunks)] + [meta_chunk]

    from app.db.models import NoteChunk  # local import to avoid cycle

    session.query(NoteChunk).filter(NoteChunk.note_id == note.id).delete()
    new_chunks = []
    for idx, (chunk_id, text) in enumerate(combined):
        new_chunks.append(NoteChunk(note_id=note.id, idx=idx, text=text, embedding=json.dumps([])))
    if new_chunks:
        session.add_all(new_chunks)
    session.flush()

    index.upsert(note.id, combined)
