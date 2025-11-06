from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db.models import Note, NoteChunk, NoteLink, NoteSource, NoteTag
from app.db.session import get_session
from app.rag.chunking import chunk_markdown
from app.rag.tfidf_index import index
from app.utils.layout_hints import dumps_layout_hints, merge_layout_hints, parse_layout_hints

router = APIRouter(tags=["notes"])


class LinkPayload(BaseModel):
    id: str
    from_id: str = Field(alias="fromId")
    to_id: str = Field(alias="toId")
    title: str
    reason: Optional[str]
    confidence: Optional[float]

    class Config:
        allow_population_by_field_name = True


class SourcePayload(BaseModel):
    id: str
    url: str
    title: str
    domain: str
    published_at: Optional[str]
    summary: Optional[str]


class NoteSummary(BaseModel):
    id: str
    title: str
    style_theme: str = Field(alias="styleTheme")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    class Config:
        allow_population_by_field_name = True


class NoteDetail(NoteSummary):
    blocks: List[Dict[str, Any]]
    layout_hints: Dict[str, Any] = Field(default_factory=dict, alias="layoutHints")
    passport: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    links_from: List[LinkPayload] = Field(default_factory=list, alias="linksFrom")
    links_to: List[LinkPayload] = Field(default_factory=list, alias="linksTo")
    sources: List[SourcePayload] = Field(default_factory=list)

    class Config(NoteSummary.Config):
        pass


class NoteListResponse(BaseModel):
    items: List[NoteSummary]
    total: int
    limit: int
    offset: int


class NoteCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    style_theme: str = Field(default="clean", alias="styleTheme")
    layout_hints: Dict[str, Any] = Field(default_factory=dict, alias="layoutHints")
    blocks: List[Dict[str, Any]] = Field(default_factory=list)
    passport: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        allow_population_by_field_name = True


class NoteUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    style_theme: Optional[str] = Field(default=None, alias="styleTheme")
    layout_hints: Optional[Dict[str, Any]] = Field(default=None, alias="layoutHints")
    blocks: Optional[List[Dict[str, Any]]] = None
    passport: Optional[Dict[str, Any]] = None

    class Config:
        allow_population_by_field_name = True


@router.get("/notes", response_model=NoteListResponse)
async def list_notes(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    with get_session() as session:
        total = session.execute(select(func.count(Note.id))).scalar_one()
        notes = (
            session.execute(
                select(Note)
                .order_by(Note.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )

        items = [_serialize_summary(note) for note in notes]
        return NoteListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/notes/{note_id}", response_model=NoteDetail)
async def get_note(note_id: str):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        return _serialize_detail(note)


@router.post("/notes", response_model=NoteDetail, status_code=201)
async def create_note(payload: NoteCreateRequest):
    with get_session() as session:
        layout_data = merge_layout_hints(None, payload.layout_hints)
        note = Note(
            title=payload.title,
            style_theme=payload.style_theme,
            layout_hints=dumps_layout_hints(layout_data),
            blocks_json=_dumps(payload.blocks),
            passport_json=_dumps(payload.passport),
        )
        session.add(note)
        session.flush()
        _reindex_note(session, note)
        session.refresh(note)
        return _serialize_detail(note)


@router.patch("/notes/{note_id}", response_model=NoteDetail)
async def update_note(note_id: str, payload: NoteUpdateRequest):
    with get_session() as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")

        blocks_changed = False

        if payload.title is not None:
            note.title = payload.title
        if payload.style_theme is not None:
            note.style_theme = payload.style_theme
        if payload.layout_hints is not None:
            merged_hints = merge_layout_hints(note.layout_hints, payload.layout_hints)
            note.layout_hints = dumps_layout_hints(merged_hints)
        if payload.blocks is not None:
            note.blocks_json = _dumps(payload.blocks)
            blocks_changed = True
        if payload.passport is not None:
            note.passport_json = _dumps(payload.passport)

        session.add(note)
        session.flush()

        if blocks_changed:
            _reindex_note(session, note)

        session.refresh(note)
        return _serialize_detail(note)


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


def _serialize_summary(note: Note) -> NoteSummary:
    return NoteSummary(
        id=note.id,
        title=note.title,
        styleTheme=note.style_theme,
        createdAt=note.created_at.isoformat(),
        updatedAt=note.updated_at.isoformat(),
    )


def _serialize_detail(note: Note) -> NoteDetail:
    blocks = json.loads(note.blocks_json or "[]")
    layout_hints = parse_layout_hints(note.layout_hints)
    passport = json.loads(note.passport_json or "{}")

    tags = [tag.tag for tag in note.tags]

    links_from = [
        LinkPayload(
            id=link.id,
            fromId=link.from_id,
            toId=link.to_id,
            title=link.target_note.title if link.target_note else "",
            reason=link.reason,
            confidence=link.confidence,
        )
        for link in note.links_from
    ]
    links_to = [
        LinkPayload(
            id=link.id,
            fromId=link.from_id,
            toId=link.to_id,
            title=link.source_note.title if link.source_note else "",
            reason=link.reason,
            confidence=link.confidence,
        )
        for link in note.links_to
    ]

    sources = [
        SourcePayload(
            id=str(ns.id),
            url=ns.source.url,
            title=ns.source.title,
            domain=ns.source.domain,
            published_at=ns.source.published_at,
            summary=ns.source.summary,
        )
        for ns in note.sources
    ]

    return NoteDetail(
        id=note.id,
        title=note.title,
        styleTheme=note.style_theme,
        createdAt=note.created_at.isoformat(),
        updatedAt=note.updated_at.isoformat(),
        blocks=blocks,
        layoutHints=layout_hints,
        passport=passport,
        tags=tags,
        linksFrom=links_from,
        linksTo=links_to,
        sources=sources,
    )


def _reindex_note(session, note: Note) -> None:
    blocks = json.loads(note.blocks_json or "[]")
    plain_text = _blocks_to_text(blocks)
    chunks = chunk_markdown(plain_text)

    session.query(NoteChunk).filter(NoteChunk.note_id == note.id).delete()
    new_chunks = []
    for idx, text in enumerate(chunks):
        new_chunks.append(
            NoteChunk(
                note_id=note.id,
                idx=float(idx),
                text=text,
                embedding="[]",
            )
        )
    if new_chunks:
        session.add_all(new_chunks)
    session.flush()

    index.upsert(note.id, [(f"{note.id}:{i}", text) for i, text in enumerate(chunks)])


def _blocks_to_text(blocks: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for block in blocks:
        b_type = block.get("type")
        data = block.get("data", {})
        if b_type == "heading":
            lines.append(str(data.get("text", "")))
        elif b_type == "paragraph":
            parts = data.get("parts", [])
            text = "".join(part.get("text", "") for part in parts)
            lines.append(text)
        elif b_type in {"bulletList", "numberList"}:
            for item in data.get("items", []):
                if isinstance(item, dict):
                    lines.append(item.get("text", ""))
                else:
                    lines.append(str(item))
        elif b_type == "quote":
            lines.append(str(data.get("text", "")))
        elif b_type == "table":
            for row in data.get("rows", []):
                if isinstance(row, list):
                    lines.append(" ".join(str(cell) for cell in row))
        elif b_type == "source":
            lines.append(str(data.get("title", "")))
            if data.get("summary"):
                lines.append(str(data.get("summary")))
        elif b_type == "summary":
            lines.append(str(data.get("text", "")))
        elif b_type == "todo":
            for item in data.get("items", []):
                if isinstance(item, dict):
                    lines.append(item.get("text", ""))
        elif b_type == "image":
            if data.get("caption"):
                lines.append(str(data.get("caption")))
        # divider and unknown types contribute no text
    return "\n".join(line for line in lines if line)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
