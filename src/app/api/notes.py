from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy import event, func, select

from app.agent.block_models import BlockModel, dump_blocks, parse_blocks
from app.api.note_models import (
    LinkPayload,
    NoteCreateRequest,
    NoteDetail,
    NoteListResponse,
    NoteSummary,
    NoteUpdateRequest,
    SourcePayload,
)
from app.db.models import FileAsset, Note, NoteChunk, NoteLink, NoteSource, NoteTag
from app.db.session import get_session
from app.rag.chunking import chunk_markdown
from app.rag.tfidf_index import index
from app.core.config import settings
from app.core.ownership import is_owned, owned_notes_filter, require_note_owner
from app.core.security import get_current_user
from app.models.user import User
from app.services.audit import log_event
from app.services.sync_protocol import check_revision, lock_stream, record_note_change, preserve_copy
from app.services.sync_engine import (
    OP_CREATE_NOTE,
    OP_DELETE_NOTE,
    OP_UPDATE_NOTE,
    enqueue_sync_operation,
)
from app.utils.layout_hints import dumps_layout_hints, merge_layout_hints, parse_layout_hints

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notes"])


def _owner_filter(user: User):
    return owned_notes_filter(user.id)


@router.get("/tags")
def list_all_tags(current_user: User = Depends(get_current_user)):
    """Возвращает список всех уникальных тегов в системе"""
    with get_session() as session:
        tags = (
            session.execute(
                select(NoteTag.tag)
                .join(Note, Note.id == NoteTag.note_id)
                .where(_owner_filter(current_user))
                .distinct()
                .order_by(NoteTag.tag)
            )
            .scalars()
            .all()
        )
        return {"tags": list(tags)}


@router.get("/notes", response_model=NoteListResponse)
def list_notes(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
):
    with get_session() as session:
        total = (
            session.execute(
                select(func.count(Note.id)).where(_owner_filter(current_user))
            )
            .scalar_one()
        )
        notes = (
            session.execute(
                select(Note)
                .where(_owner_filter(current_user))
                .order_by(Note.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )

        items = [_serialize_summary(note) for note in notes]
        return NoteListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/notes/search/full")
def search_notes_full(
    q: str = Query(..., min_length=1, max_length=512),
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Extended search: TF-IDF content search + title search + file name search."""
    from app.services.rate_limit import limit_operation
    limit_operation('search', current_user.id, settings.rate_limit_search_per_min)
    query_lower = q.strip().lower()
    matched_note_ids: dict[str, float] = {}

    with get_session() as session:
        user_note_ids = set(
            row[0]
            for row in session.execute(
                select(Note.id).where(_owner_filter(current_user))
            ).all()
        )

        # Release the read transaction before any CPU-heavy index fit.
        session.commit()
        # Filter before ranking so tombstones/other owners cannot crowd out hits.
        for result in index.search(q, limit=limit, allowed_note_ids=user_note_ids):
            nid, score = result["note_id"], result["score"]
            if nid not in matched_note_ids or score > matched_note_ids[nid]:
                matched_note_ids[nid] = score

        # 2. Title search (SQL LIKE)
        title_matches = (
            session.execute(
                select(Note.id).where(
                    _owner_filter(current_user),
                    func.lower(Note.title).contains(query_lower),
                )
            )
            .scalars()
            .all()
        )
        for nid in title_matches:
            if nid not in matched_note_ids:
                matched_note_ids[nid] = 0.5

        # 3. File name search
        file_matches = (
            session.execute(
                select(FileAsset.note_id).where(
                    FileAsset.note_id.isnot(None),
                    FileAsset.user_id == current_user.id,
                    func.lower(FileAsset.filename).contains(query_lower),
                )
            )
            .scalars()
            .all()
        )
        for nid in file_matches:
            if nid and nid not in matched_note_ids:
                matched_note_ids[nid] = 0.4

        # Filter to only user's notes and sort by relevance
        final_ids = [
            nid for nid in matched_note_ids if nid in user_note_ids
        ]
        final_ids.sort(key=lambda nid: matched_note_ids[nid], reverse=True)
        final_ids = final_ids[:limit]

        if not final_ids:
            return {"items": [], "total": 0, "query": q}

        notes = (
            session.execute(select(Note).where(Note.id.in_(final_ids), _owner_filter(current_user)))
            .scalars()
            .all()
        )
        notes_map = {n.id: n for n in notes}
        ordered = [notes_map[nid] for nid in final_ids if nid in notes_map]
        items = [
            _serialize_summary(n).dict(by_alias=True)
            for n in ordered
        ]

        return {"items": items, "total": len(items), "query": q}


@router.get("/notes/{note_id}", response_model=NoteDetail)
def get_note(note_id: str, request: Request, response: Response, current_user: User = Depends(get_current_user)):
    with get_session() as session:
        note = session.execute(
            select(Note).where(Note.id == note_id)
        ).scalars().first()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        _ensure_note_owner(note, current_user, session)
        response.headers["ETag"] = f'"r{note.revision}"'
        log_event(session, "NOTE_READ", user_id=current_user.id, request=request, metadata={"note_id": note.id})
        return _serialize_detail(note, session=session, user_id=current_user.id)


@router.post("/notes", response_model=NoteDetail, status_code=201)
def create_note(payload: NoteCreateRequest, request: Request, response: Response, current_user: User = Depends(get_current_user)):
    with get_session(immediate=True) as session:
        lock_stream(session)
        layout_data = merge_layout_hints(None, payload.layout_hints)
        note = Note(
            title=payload.title,
            style_theme=payload.style_theme,
            layout_hints=dumps_layout_hints(layout_data),
            blocks_json=_dumps_blocks(payload.blocks),
            passport_json=_dumps(payload.passport),
            user_id=current_user.id,
        )
        session.add(note)
        session.flush()
        _reindex_note(session, note)
        session.refresh(note)
        record_note_change(session, note, "create")
        enqueue_sync_operation(
            session,
            OP_CREATE_NOTE,
            {
                "localNoteId": note.id,
                "note": {
                    "title": note.title,
                    "styleTheme": note.style_theme,
                    "layoutHints": parse_layout_hints(note.layout_hints),
                    "blocks": _load_blocks(note.blocks_json, note_id=note.id),
                    "passport": json.loads(note.passport_json or "{}"),
                },
            },
            note_id=note.id,
            user_id=current_user.id,
        )
        log_event(session, "NOTE_CREATE", user_id=current_user.id, request=request, metadata={"note_id": note.id})
        response.headers["ETag"] = f'"r{note.revision}"'
        return _serialize_detail(note, session=session, user_id=current_user.id)


@router.post("/notes/{note_id}/recovery-copy", response_model=NoteDetail, status_code=201)
def recover_note(note_id: str, payload: NoteCreateRequest, request: Request,
                       response: Response, current_user: User = Depends(get_current_user)):
    with get_session(immediate=True) as session:
        lock_stream(session)
        original = session.get(Note, note_id)
        # A preserved draft remains recoverable after its own original is deleted.
        if not original or original.user_id != current_user.id:
            raise HTTPException(404, 'Note not found')
        copy = preserve_copy(session, current_user.id, payload.model_dump(by_alias=True),
                             title_suffix=' (восстановлено)')
        enqueue_sync_operation(session, OP_CREATE_NOTE, {}, note_id=copy.id, user_id=current_user.id)
        log_event(session, 'NOTE_RECOVERY_COPY', user_id=current_user.id, request=request,
                  metadata={'note_id': copy.id, 'original_id': note_id})
        response.headers['ETag'] = f'"r{copy.revision}"'
        return _serialize_detail(copy, session=session, user_id=current_user.id)


@router.patch("/notes/{note_id}", response_model=NoteDetail)
def update_note(
    note_id: str,
    payload: NoteUpdateRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    with get_session(immediate=True) as session:
        lock_stream(session)
        note = session.execute(select(Note).where(Note.id == note_id).with_for_update()).scalars().first()
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        _ensure_note_owner(note, current_user, session)

        check_revision(note, request.headers.get("If-Match"))

        blocks_changed = False

        if payload.title is not None:
            note.title = payload.title
        if payload.style_theme is not None:
            note.style_theme = payload.style_theme
        if payload.layout_hints is not None:
            merged_hints = merge_layout_hints(note.layout_hints, payload.layout_hints)
            note.layout_hints = dumps_layout_hints(merged_hints)
        if payload.blocks is not None:
            note.blocks_json = _dumps_blocks(payload.blocks)
            blocks_changed = True
        if payload.passport is not None:
            note.passport_json = _dumps(payload.passport)

        patch_payload: Dict[str, Any] = {}
        if payload.title is not None:
            patch_payload["title"] = payload.title
        if payload.style_theme is not None:
            patch_payload["styleTheme"] = payload.style_theme
        if payload.layout_hints is not None:
            patch_payload["layoutHints"] = payload.layout_hints
        if payload.blocks is not None:
            patch_payload["blocks"] = dump_blocks(payload.blocks)
        if payload.passport is not None:
            patch_payload["passport"] = payload.passport

        session.add(note)
        session.flush()

        if blocks_changed:
            _reindex_note(session, note)

        session.refresh(note)
        record_note_change(session, note)
        enqueue_sync_operation(
            session,
            OP_UPDATE_NOTE,
            {
                "localNoteId": note.id,
                "patch": patch_payload,
                "snapshot": _serialize_detail(note, session=session, user_id=current_user.id).dict(by_alias=True),
            },
            note_id=note.id,
            user_id=current_user.id,
        )
        log_event(session, "NOTE_UPDATE", user_id=current_user.id, request=request, metadata={"note_id": note.id})
        response.headers["ETag"] = f'"r{note.revision}"'
        return _serialize_detail(note, session=session, user_id=current_user.id)


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, request: Request, current_user: User = Depends(get_current_user)):
    with get_session(immediate=True) as session:
        lock_stream(session)
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        _ensure_note_owner(note, current_user, session)
        check_revision(note, request.headers.get("If-Match"))
        note.tombstone = True
        record_note_change(session, note, "delete")
        enqueue_sync_operation(
            session,
            OP_DELETE_NOTE,
            {"localNoteId": note.id},
            note_id=note.id,
            user_id=current_user.id,
        )
        log_event(session, "NOTE_DELETE", user_id=current_user.id, request=request, metadata={"note_id": note.id})
    index.remove(note_id)
    return {"status": "ok"}


def _serialize_summary(note: Note) -> NoteSummary:
    return NoteSummary(
        id=note.id,
        title=note.title,
        styleTheme=note.style_theme,
        createdAt=note.created_at.isoformat(),
        updatedAt=note.updated_at.isoformat(),
        revision=note.revision,
    )


def _serialize_detail(note: Note, session=None, user_id: Optional[str] = None) -> NoteDetail:
    blocks = _load_blocks(note.blocks_json, note_id=note.id)
    layout_hints = parse_layout_hints(note.layout_hints)
    passport = json.loads(note.passport_json or "{}")

    # Загружаем теги отдельным запросом, если передана сессия
    if session:
        tags = [
            row.tag
            for row in session.execute(
                select(NoteTag.tag).where(NoteTag.note_id == note.id)
            ).all()
        ]
    else:
        tags = [tag.tag for tag in note.tags]

    links_from = []
    for link in note.links_from:
        if not is_owned(link.target_note, user_id or note.user_id):
            continue
        links_from.append(
            LinkPayload(
                id=link.id,
                fromId=link.from_id,
                toId=link.to_id,
                title=link.target_note.title if link.target_note else "",
                reason=link.reason,
                confidence=link.confidence,
            )
        )
    links_to = []
    for link in note.links_to:
        if not is_owned(link.source_note, user_id or note.user_id):
            continue
        links_to.append(
            LinkPayload(
                id=link.id,
                fromId=link.from_id,
                toId=link.to_id,
                title=link.source_note.title if link.source_note else "",
                reason=link.reason,
                confidence=link.confidence,
            )
        )

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
        revision=note.revision,
        blocks=blocks,
        layoutHints=layout_hints,
        passport=passport,
        tags=tags,
        linksFrom=links_from,
        linksTo=links_to,
        sources=sources,
    )


def _ensure_note_owner(note: Note, user: User, session) -> None:
    require_note_owner(note, user.id)


def _reindex_note(session, note: Note) -> None:
    blocks = _load_blocks(note.blocks_json, note_id=note.id)
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

    # The cache must not publish content from a transaction later rejected by
    # the journal/outbox (e.g. queue overflow).
    note_id = note.id
    indexed_chunks = [(f"{note_id}:{i}", text) for i, text in enumerate(chunks)]
    event.listen(session, "after_commit", lambda _: index.upsert(note_id, indexed_chunks), once=True)


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


def _dumps_blocks(blocks: List[BlockModel]) -> str:
    return _dumps(dump_blocks(blocks))


def _load_blocks(raw_json: str, *, note_id: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        parsed = json.loads(raw_json or "[]")
    except json.JSONDecodeError as exc:
        logger.warning("Failed to decode blocks JSON for note %s: %s", note_id, exc)
        raise HTTPException(status_code=409, detail="Stored block JSON is damaged; original data retained") from exc

    if not isinstance(parsed, list):
        logger.warning("Blocks JSON for note %s is not a list", note_id)
        raise HTTPException(status_code=409, detail="Stored blocks must be a list; original data retained")

    try:
        typed_blocks = parse_blocks(parsed)
    except ValidationError as exc:
        logger.warning("Block schema validation failed for note %s; retaining original JSON", note_id)
        return parsed
    return dump_blocks(typed_blocks)
