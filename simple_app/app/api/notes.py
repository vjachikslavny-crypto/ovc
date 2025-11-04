from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import Note
from app.db.session import get_session
from app.rag.tfidf_index import index
from app.rag.chunking import chunk_markdown

router = APIRouter(tags=["notes"])


class NoteCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content_md: str = Field(..., min_length=1)


class NoteUpdateRequest(BaseModel):
    title: str | None = None
    content_md: str | None = None


class NoteResponse(BaseModel):
    id: str
    title: str
    content_md: str


@router.get("/notes", response_model=list[NoteResponse])
async def list_notes():
    with get_session() as session:
        notes = session.execute(select(Note)).scalars().all()
    return [NoteResponse(id=n.id, title=n.title, content_md=n.content_md) for n in notes]


@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(note_id: str):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        return NoteResponse(id=note.id, title=note.title, content_md=note.content_md)


@router.post("/notes", response_model=NoteResponse)
async def create_note(payload: NoteCreateRequest):
    with get_session() as session:
        note = Note(title=payload.title, content_md=payload.content_md)
        session.add(note)
        session.flush()
        _reindex(note)
        return NoteResponse(id=note.id, title=note.title, content_md=note.content_md)


@router.patch("/notes/{note_id}", response_model=NoteResponse)
async def update_note(note_id: str, payload: NoteUpdateRequest):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        if payload.title:
            note.title = payload.title
        if payload.content_md:
            note.content_md = payload.content_md
        session.add(note)
        session.flush()
        _reindex(note)
        return NoteResponse(id=note.id, title=note.title, content_md=note.content_md)


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        session.delete(note)
        session.flush()
        index.remove(note_id)
    return {"status": "ok"}


def _reindex(note: Note) -> None:
    chunks = chunk_markdown(note.content_md)
    index.upsert(note.id, [(f"{note.id}:{idx}", text) for idx, text in enumerate(chunks)])
