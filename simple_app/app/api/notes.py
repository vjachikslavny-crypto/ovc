from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import Note, NoteLink, NoteSource, NoteTag
from app.db.session import get_session
from app.rag.chunking import chunk_markdown
from app.rag.tfidf_index import index

router = APIRouter(tags=["notes"])


class NoteTagResponse(BaseModel):
    tag: str
    weight: float


class NoteLinkResponse(BaseModel):
    id: str
    from_id: str
    to_id: str
    to_title: str
    reason: str
    confidence: float


class NoteResponse(BaseModel):
    id: str
    title: str
    content_md: str
    priority: str
    status: str
    importance: float
    cluster: str
    cluster_color: str
    tags: List[NoteTagResponse] = []


class NoteDetailResponse(NoteResponse):
    links_from: List[NoteLinkResponse] = []
    links_to: List[NoteLinkResponse] = []
    sources: List[dict] = []


class NoteCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content_md: str = Field(..., min_length=1)
    priority: str = Field(default="medium")
    importance: float = Field(default=1.0, ge=0.4, le=3.0)
    cluster: str = Field(default="default", max_length=48)
    cluster_color: str = Field(default="#8b5cf6", min_length=4, max_length=16)


class NoteUpdateRequest(BaseModel):
    title: Optional[str] = None
    content_md: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    importance: Optional[float] = Field(default=None, ge=0.4, le=3.0)
    cluster: Optional[str] = Field(default=None, max_length=48)
    cluster_color: Optional[str] = Field(default=None, min_length=4, max_length=16)


class TagRequest(BaseModel):
    tag: str = Field(..., min_length=1)
    weight: float = Field(default=1.0, ge=0.1)


class LinkRequest(BaseModel):
    target_id: str = Field(..., min_length=1)
    reason: str = Field(default="manual")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


@router.get("/notes", response_model=List[NoteResponse])
async def list_notes():
    items: List[NoteResponse] = []
    with get_session() as session:
        notes = session.execute(select(Note)).scalars().all()
        for note in notes:
            items.append(_serialize_note(note, include_links=False, include_sources=False))
    return items


@router.get("/notes/{note_id}", response_model=NoteDetailResponse)
async def get_note(note_id: str):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        return _serialize_note(note, include_links=True, include_sources=True)


@router.post("/notes", response_model=NoteDetailResponse)
async def create_note(payload: NoteCreateRequest):
    with get_session() as session:
        note = Note(
            title=payload.title,
            content_md=payload.content_md,
            priority=payload.priority,
            importance=payload.importance,
            cluster=payload.cluster or "default",
            cluster_color=payload.cluster_color or "#8b5cf6",
        )
        session.add(note)
        session.flush()
        _reindex(session, note)
        session.refresh(note)
        return _serialize_note(note, include_links=True, include_sources=True)


@router.patch("/notes/{note_id}", response_model=NoteDetailResponse)
async def update_note(note_id: str, payload: NoteUpdateRequest):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        if payload.title is not None:
            note.title = payload.title
        if payload.content_md is not None:
            note.content_md = payload.content_md
        if payload.priority is not None:
            note.priority = payload.priority
        if payload.status is not None:
            note.status = payload.status
        if payload.importance is not None:
            note.importance = payload.importance
        if payload.cluster is not None:
            note.cluster = payload.cluster or "default"
        if payload.cluster_color is not None:
            note.cluster_color = payload.cluster_color or "#8b5cf6"
        session.add(note)
        session.flush()
        _reindex(session, note)
        session.refresh(note)
        return _serialize_note(note, include_links=True, include_sources=True)


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


@router.post("/notes/{note_id}/tags", response_model=NoteDetailResponse)
async def add_tag(note_id: str, payload: TagRequest):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        tag = session.execute(
            select(NoteTag).where(NoteTag.note_id == note_id, NoteTag.tag == payload.tag)
        ).scalar_one_or_none()
        if tag:
            tag.weight = payload.weight
        else:
            session.add(NoteTag(note_id=note_id, tag=payload.tag, weight=payload.weight))
        session.flush()
        _reindex(session, note)
        session.refresh(note)
        return _serialize_note(note, include_links=True, include_sources=True)


@router.delete("/notes/{note_id}/tags/{tag}", response_model=NoteDetailResponse)
async def remove_tag(note_id: str, tag: str):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        session.query(NoteTag).filter(NoteTag.note_id == note_id, NoteTag.tag == tag).delete()
        session.flush()
        _reindex(session, note)
        session.refresh(note)
        return _serialize_note(note, include_links=True, include_sources=True)


@router.post("/notes/{note_id}/links", response_model=NoteDetailResponse)
async def add_link(note_id: str, payload: LinkRequest):
    with get_session() as session:
        source = session.get(Note, note_id)
        target = session.get(Note, payload.target_id)
        if not source or not target:
            raise HTTPException(status_code=404, detail="Note not found")
        existing = session.execute(
            select(NoteLink).where(
                NoteLink.from_id == note_id,
                NoteLink.to_id == payload.target_id,
                NoteLink.reason == payload.reason,
            )
        ).scalar_one_or_none()
        if not existing:
            session.add(
                NoteLink(
                    from_id=note_id,
                    to_id=payload.target_id,
                    reason=payload.reason,
                    confidence=payload.confidence,
                )
            )
        session.flush()
        session.refresh(source)
        return _serialize_note(source, include_links=True, include_sources=True)


@router.delete("/notes/{note_id}/links/{link_id}", response_model=NoteDetailResponse)
async def remove_link(note_id: str, link_id: str):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        session.query(NoteLink).filter(NoteLink.id == link_id, NoteLink.from_id == note_id).delete()
        session.flush()
        session.refresh(note)
        return _serialize_note(note, include_links=True, include_sources=True)


def _serialize_note(note: Note, include_links: bool, include_sources: bool) -> NoteDetailResponse:
    tags = [NoteTagResponse(tag=tag.tag, weight=tag.weight) for tag in note.tags]

    links_from: List[NoteLinkResponse] = []
    links_to: List[NoteLinkResponse] = []

    if include_links:
        for link in note.links_from:
            target_title = link.target_note.title if link.target_note else ""
            links_from.append(
                NoteLinkResponse(
                    id=link.id,
                    from_id=link.from_id,
                    to_id=link.to_id,
                    to_title=target_title,
                    reason=link.reason,
                    confidence=link.confidence,
                )
            )
        for link in note.links_to:
            source_title = link.source_note.title if link.source_note else ""
            links_to.append(
                NoteLinkResponse(
                    id=link.id,
                    from_id=link.from_id,
                    to_id=link.to_id,
                    to_title=source_title,
                    reason=link.reason,
                    confidence=link.confidence,
                )
            )

    sources_payload: List[dict] = []
    if include_sources:
        for note_source in note.sources:
            src = note_source.source
            sources_payload.append(
                {
                    "id": src.id,
                    "url": src.url,
                    "domain": src.domain,
                    "title": src.title,
                    "summary": src.summary,
                    "published_at": src.published_at,
                }
            )

    return NoteDetailResponse(
        id=note.id,
        title=note.title,
        content_md=note.content_md,
        priority=note.priority,
        status=note.status,
        importance=note.importance,
        cluster=note.cluster,
        cluster_color=note.cluster_color,
        tags=tags,
        links_from=links_from,
        links_to=links_to,
        sources=sources_payload,
    )


def _reindex(session, note: Note) -> None:
    tags = [tag.tag for tag in note.tags]
    additional = [
        (f"{note.id}:meta", f"{note.title}\nTags: {', '.join(tags)}\nPriority: {note.priority}\nStatus: {note.status}")
    ]
    chunks = chunk_markdown(note.content_md)
    all_chunks = [(f"{note.id}:{idx}", text) for idx, text in enumerate(chunks)] + additional

    from app.db.models import NoteChunk  # local import to avoid circular

    session.query(NoteChunk).filter(NoteChunk.note_id == note.id).delete()
    new_chunks = []
    for chunk_id, text in all_chunks:
        new_chunks.append(
            NoteChunk(note_id=note.id, idx=len(new_chunks), text=text, embedding="[]")
        )
    if new_chunks:
        session.add_all(new_chunks)
    session.flush()

    index.upsert(note.id, all_chunks)
