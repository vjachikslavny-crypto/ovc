from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.db.models import Note, NoteTag, SyncConflict, SyncNoteMap, SyncOutbox
from app.db.session import get_session

logger = logging.getLogger(__name__)

OP_CREATE_NOTE = "create_note"
OP_UPDATE_NOTE = "update_note"
OP_DELETE_NOTE = "delete_note"
OP_COMMIT = "commit"
OP_UPLOAD_FILE = "upload_file"

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

_MAX_RETRIES_BEFORE_BACKOFF = 5

_worker_lock = threading.Lock()
_sync_lock = threading.Lock()
_worker_started = False
_sync_thread: Optional[threading.Thread] = None


class RetryableSyncError(Exception):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _parse_iso_utc(value: str) -> datetime:
    if not value:
        return datetime.min
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


@contextmanager
def _sync_guard():
    with _sync_lock:
        yield


def start_sync_worker_once() -> None:
    global _worker_started, _sync_thread

    if settings.sync_mode in {"off", "shared-db", "remote-shell"}:
        logger.info(
            "sync worker disabled: mode=%s (remote_configured=%s)",
            settings.sync_mode,
            settings.sync_remote_configured,
        )
        return

    if not settings.sync_worker_enabled:
        logger.warning(
            "sync worker disabled: mode=%s requires SYNC_BEARER_TOKEN for background sync",
            settings.sync_mode,
        )
        return

    with _worker_lock:
        if _worker_started:
            return

        def _loop() -> None:
            base_delay = max(3, settings.sync_poll_seconds)
            delay = base_delay
            while True:
                try:
                    trigger_sync_now()
                    delay = base_delay
                except Exception as exc:
                    logger.warning("sync worker cycle failed: %s", exc)
                    delay = min(max(base_delay, delay * 2), 120)
                threading.Event().wait(delay)

        _sync_thread = threading.Thread(target=_loop, name="ovc-sync-worker", daemon=True)
        _sync_thread.start()
        _worker_started = True
        logger.info(
            "sync worker started (mode=%s poll=%ss remote=%s)",
            settings.sync_mode,
            settings.sync_poll_seconds,
            bool(settings.sync_remote_base_url),
        )


def enqueue_sync_operation(
    session,
    op_type: str,
    payload: Dict[str, Any],
    *,
    note_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    if not (settings.desktop_mode or settings.sync_enabled):
        return

    active_count = (
        session.execute(
            select(func.count(SyncOutbox.id)).where(SyncOutbox.status.in_([STATUS_PENDING, STATUS_FAILED]))
        ).scalar_one()
        or 0
    )
    if active_count >= settings.sync_outbox_max:
        logger.warning("sync outbox is full (%s), skip enqueue op=%s", active_count, op_type)
        return

    item = SyncOutbox(
        op_type=op_type,
        user_id=user_id,
        note_id=note_id,
        payload_json=json.dumps(payload, ensure_ascii=False),
        status=STATUS_PENDING,
        tries=0,
    )
    session.add(item)


def trigger_sync_now(
    *,
    access_token: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    if settings.sync_mode in {"off", "shared-db"}:
        return {"ok": False, "reason": f"sync_mode_{settings.sync_mode}"}
    if not settings.sync_remote_base_url:
        return {"ok": False, "reason": "remote_base_url_empty"}
    if user_id and settings.desktop_mode and not (access_token or "").strip():
        return {"ok": False, "reason": "missing_user_access_token"}
    if user_id and not (access_token or settings.sync_bearer_token):
        return {"ok": False, "reason": "missing_sync_auth_token"}

    with _sync_guard():
        with get_session() as session:
            client = _build_client(access_token=access_token)
            pushed, failed = _push_outbox(session, client, user_id=user_id)
            pulled = 0
            conflicts = 0
            if settings.sync_pull_enabled:
                pulled, conflicts = _pull_remote_changes(session, client, user_id=user_id)

            return {
                "ok": True,
                "pushed": pushed,
                "failed": failed,
                "pulled": pulled,
                "conflicts": conflicts,
            }


def get_sync_status(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    with get_session() as session:
        base_filter = []
        if user_id:
            base_filter.append(SyncOutbox.user_id == user_id)

        pending = (
            session.execute(
                select(func.count(SyncOutbox.id)).where(SyncOutbox.status == STATUS_PENDING, *base_filter)
            ).scalar_one()
            or 0
        )
        failed = (
            session.execute(
                select(func.count(SyncOutbox.id)).where(SyncOutbox.status == STATUS_FAILED, *base_filter)
            ).scalar_one()
            or 0
        )
        done = (
            session.execute(
                select(func.count(SyncOutbox.id)).where(SyncOutbox.status == STATUS_DONE, *base_filter)
            ).scalar_one()
            or 0
        )
        conflicts = session.execute(select(func.count(SyncConflict.id))).scalar_one() or 0

    return {
        "enabled": bool(settings.sync_mode in {"remote-sync", "remote-shell"}),
        "mode": settings.sync_mode,
        "workerEnabled": settings.sync_worker_enabled,
        "desktopMode": settings.desktop_mode,
        "syncEnabledFlag": settings.sync_enabled,
        "remoteConfigured": bool(settings.sync_remote_base_url),
        "remoteBaseUrl": settings.sync_remote_base_url,
        "pending": pending,
        "failed": failed,
        "done": done,
        "conflicts": conflicts,
    }


def _build_client(*, access_token: Optional[str] = None) -> httpx.Client:
    headers: Dict[str, str] = {}
    token = (access_token or "").strip() or settings.sync_bearer_token
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return httpx.Client(
        base_url=settings.sync_remote_base_url.rstrip("/"),
        timeout=settings.sync_request_timeout_seconds,
        headers=headers,
    )


def _push_outbox(session, client: httpx.Client, *, user_id: Optional[str] = None) -> Tuple[int, int]:
    query = (
        select(SyncOutbox)
        .where(SyncOutbox.status.in_([STATUS_PENDING, STATUS_FAILED]))
        .order_by(SyncOutbox.created_at.asc())
        .limit(settings.sync_batch_size)
    )
    if user_id:
        query = query.where(or_(SyncOutbox.user_id == user_id, SyncOutbox.user_id.is_(None)))

    items = session.execute(query).scalars().all()

    pushed = 0
    failed = 0
    for item in items:
        try:
            payload = json.loads(item.payload_json or "{}")

            if user_id and not _operation_belongs_to_user(session, item, payload, user_id):
                continue
            if user_id and not item.user_id:
                item.user_id = user_id
                session.add(item)

            _flush_operation(session, client, item, payload)
            item.status = STATUS_DONE
            item.last_error = None
            item.updated_at = _now()
            session.flush()
            pushed += 1
        except RetryableSyncError as exc:
            item.status = STATUS_FAILED
            item.tries = (item.tries or 0) + 1
            item.last_error = str(exc)
            item.updated_at = _now()
            failed += 1
            if item.tries >= _MAX_RETRIES_BEFORE_BACKOFF:
                logger.warning("sync op id=%s type=%s retry=%s err=%s", item.id, item.op_type, item.tries, exc)
            break
        except Exception as exc:  # noqa: BLE001
            item.status = STATUS_FAILED
            item.tries = (item.tries or 0) + 1
            item.last_error = str(exc)
            item.updated_at = _now()
            failed += 1
            logger.warning("sync op id=%s type=%s failed: %s", item.id, item.op_type, exc)

    session.flush()
    return pushed, failed


def _flush_operation(session, client: httpx.Client, item: SyncOutbox, payload: Dict[str, Any]) -> None:
    op_type = item.op_type

    if op_type == OP_CREATE_NOTE:
        _flush_create_note(session, client, item, payload)
        return
    if op_type == OP_UPDATE_NOTE:
        _flush_update_note(session, client, payload)
        return
    if op_type == OP_DELETE_NOTE:
        _flush_delete_note(session, client, payload)
        return
    if op_type == OP_COMMIT:
        _flush_commit(session, client, payload)
        return
    if op_type == OP_UPLOAD_FILE:
        _flush_upload_file(session, client, item, payload)
        return

    raise RuntimeError(f"unsupported op type: {op_type}")


def _flush_create_note(session, client: httpx.Client, item: SyncOutbox, payload: Dict[str, Any]) -> None:
    local_note_id = payload.get("localNoteId")
    note_payload = payload.get("note") or {}
    if not local_note_id:
        raise RuntimeError("create_note payload missing localNoteId")

    existing_remote = _get_remote_note_id(session, local_note_id)
    if existing_remote:
        return

    response = client.post("/api/notes", json=note_payload, headers={"X-Desktop-Op-Id": item.id})
    if response.status_code >= 400:
        raise RetryableSyncError(f"remote create failed: {response.status_code} {response.text}")

    remote_id = response.json().get("id")
    if not remote_id:
        raise RuntimeError("remote create response missing id")
    _set_note_map(session, local_note_id, remote_id)


def _flush_update_note(session, client: httpx.Client, payload: Dict[str, Any]) -> None:
    local_note_id = payload.get("localNoteId")
    patch = payload.get("patch") or {}
    snapshot = payload.get("snapshot") or None
    if not local_note_id:
        raise RuntimeError("update_note payload missing localNoteId")

    remote_id = _get_remote_note_id(session, local_note_id) or local_note_id
    response = client.patch(f"/api/notes/{remote_id}", json=patch)
    if response.status_code == 404 and snapshot:
        create_payload = {
            "title": snapshot.get("title") or "Новая заметка",
            "styleTheme": snapshot.get("styleTheme") or "clean",
            "layoutHints": snapshot.get("layoutHints") or {},
            "blocks": snapshot.get("blocks") or [],
            "passport": snapshot.get("passport") or {},
        }
        created = client.post("/api/notes", json=create_payload)
        if created.status_code >= 400:
            raise RetryableSyncError(
                f"remote create for update fallback failed: {created.status_code} {created.text}"
            )
        created_id = created.json().get("id")
        if created_id:
            _set_note_map(session, local_note_id, created_id)
        return

    if response.status_code >= 400:
        raise RetryableSyncError(f"remote update failed: {response.status_code} {response.text}")


def _flush_delete_note(session, client: httpx.Client, payload: Dict[str, Any]) -> None:
    local_note_id = payload.get("localNoteId")
    if not local_note_id:
        raise RuntimeError("delete_note payload missing localNoteId")

    remote_id = _get_remote_note_id(session, local_note_id) or local_note_id
    response = client.delete(f"/api/notes/{remote_id}")
    if response.status_code not in (200, 404):
        raise RetryableSyncError(f"remote delete failed: {response.status_code} {response.text}")


def _flush_commit(session, client: httpx.Client, payload: Dict[str, Any]) -> None:
    draft = payload.get("draft")
    if not isinstance(draft, list):
        raise RuntimeError("commit payload missing draft list")

    mapped_draft = [_map_action_ids(session, action) for action in draft]
    response = client.post("/api/commit", json={"draft": mapped_draft})
    if response.status_code >= 400:
        raise RetryableSyncError(f"remote commit failed: {response.status_code} {response.text}")


def _flush_upload_file(
    session,
    client: httpx.Client,
    item: SyncOutbox,
    payload: Dict[str, Any],
) -> None:
    local_note_id = payload.get("localNoteId")
    file_path = payload.get("filePath")
    file_asset_id = payload.get("fileAssetId") or ""
    filename = payload.get("filename") or "upload"
    mime = payload.get("mime") or "application/octet-stream"

    if not local_note_id or not file_path:
        raise RuntimeError("upload_file payload missing localNoteId/filePath")

    remote_note_id = _get_remote_note_id(session, local_note_id)
    if not remote_note_id:
        has_pending_create = (
            session.execute(
                select(func.count(SyncOutbox.id)).where(
                    SyncOutbox.op_type == OP_CREATE_NOTE,
                    SyncOutbox.note_id == local_note_id,
                    SyncOutbox.status.in_([STATUS_PENDING, STATUS_FAILED]),
                )
            ).scalar_one()
            or 0
        )
        if has_pending_create:
            raise RetryableSyncError(
                f"note mapping for upload {local_note_id} is not ready yet"
            )
        remote_note_id = local_note_id

    try:
        with open(file_path, "rb") as f:
            files = {"files": (filename, f, mime)}
            response = client.post(
                f"/api/upload?noteId={remote_note_id}",
                files=files,
                headers={
                    "X-Desktop-File-Id": str(file_asset_id),
                    "X-Desktop-Op-Id": item.id,
                },
            )
    except FileNotFoundError as exc:
        raise RuntimeError(f"local file missing: {file_path}") from exc

    if response.status_code >= 400:
        raise RetryableSyncError(f"remote upload failed: {response.status_code} {response.text}")


def _map_action_ids(session, action: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(action, dict):
        return action

    mapped = dict(action)
    for key in ("noteId", "fromId", "toId"):
        value = mapped.get(key)
        if not value:
            continue
        remote = _get_remote_note_id(session, value)
        if remote:
            mapped[key] = remote
        else:
            has_pending_create = (
                session.execute(
                    select(func.count(SyncOutbox.id)).where(
                        SyncOutbox.op_type == OP_CREATE_NOTE,
                        SyncOutbox.note_id == value,
                        SyncOutbox.status.in_([STATUS_PENDING, STATUS_FAILED]),
                    )
                ).scalar_one()
                or 0
            )
            if has_pending_create:
                raise RetryableSyncError(f"note mapping for {value} is not ready yet")
    return mapped


def _pull_remote_changes(
    session,
    client: httpx.Client,
    *,
    user_id: Optional[str] = None,
) -> Tuple[int, int]:
    pulled = 0
    conflicts = 0
    offset = 0
    limit = 100

    while True:
        response = client.get(f"/api/notes?limit={limit}&offset={offset}")
        if response.status_code >= 400:
            raise RetryableSyncError(f"remote pull list failed: {response.status_code} {response.text}")

        payload = response.json() or {}
        items = payload.get("items") or []
        if not items:
            break

        for item in items:
            remote_id = item.get("id")
            if not remote_id:
                continue

            local_id = _get_local_note_id(session, remote_id) or remote_id
            local_note = session.get(Note, local_id)
            pending_for_note = _has_pending_note_ops(session, local_id)
            remote_updated = _parse_iso_utc(item.get("updatedAt") or "")

            if local_note and pending_for_note and remote_updated > (local_note.updated_at or datetime.min):
                _create_conflict_copy(session, local_note, remote_id)
                _drop_pending_note_ops(session, local_note.id)
                conflicts += 1

            if pending_for_note:
                continue

            detail = _fetch_remote_note_detail(client, remote_id)
            if local_note is None:
                _upsert_local_note_from_remote(session, local_id, detail, user_id=user_id)
                _set_note_map(session, local_id, remote_id)
                pulled += 1
                continue

            local_updated = local_note.updated_at or datetime.min
            if remote_updated > local_updated:
                _upsert_local_note_from_remote(session, local_id, detail, user_id=user_id)
                _set_note_map(session, local_id, remote_id)
                pulled += 1

        total = payload.get("total") or 0
        offset += len(items)
        if offset >= total:
            break

    return pulled, conflicts


def _fetch_remote_note_detail(client: httpx.Client, remote_id: str) -> Dict[str, Any]:
    response = client.get(f"/api/notes/{remote_id}")
    if response.status_code >= 400:
        raise RetryableSyncError(f"remote pull detail failed: {response.status_code} {response.text}")
    return response.json() or {}


def _upsert_local_note_from_remote(
    session,
    local_id: str,
    detail: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
) -> None:
    note = session.get(Note, local_id)
    if note is None:
        note = Note(id=local_id)
    if user_id:
        note.user_id = user_id

    note.title = detail.get("title") or "Новая заметка"
    note.style_theme = detail.get("styleTheme") or "clean"
    note.layout_hints = json.dumps(detail.get("layoutHints") or {}, ensure_ascii=False)
    note.blocks_json = json.dumps(detail.get("blocks") or [], ensure_ascii=False)
    note.passport_json = json.dumps(detail.get("passport") or {}, ensure_ascii=False)

    updated_at = _parse_iso_utc(detail.get("updatedAt") or "")
    created_at = _parse_iso_utc(detail.get("createdAt") or "")
    note.updated_at = updated_at if updated_at != datetime.min else _now()
    note.created_at = created_at if created_at != datetime.min else note.updated_at

    session.add(note)
    session.flush()

    session.query(NoteTag).filter(NoteTag.note_id == note.id).delete()
    tags = detail.get("tags") or []
    for tag in tags:
        session.add(NoteTag(note_id=note.id, tag=str(tag)))


def _create_conflict_copy(session, note: Note, remote_note_id: str) -> None:
    copy_note = Note(
        title=f"{note.title} (conflict copy)",
        style_theme=note.style_theme,
        layout_hints=note.layout_hints,
        blocks_json=note.blocks_json,
        passport_json=note.passport_json,
        user_id=note.user_id,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(copy_note)
    session.flush()

    conflict = SyncConflict(
        local_note_id=note.id,
        remote_note_id=remote_note_id,
        kind="lww_conflict_copy",
        payload_json=json.dumps(
            {
                "localNoteId": note.id,
                "conflictCopyId": copy_note.id,
                "remoteNoteId": remote_note_id,
            },
            ensure_ascii=False,
        ),
    )
    session.add(conflict)


def _drop_pending_note_ops(session, local_note_id: str) -> None:
    rows = (
        session.execute(
            select(SyncOutbox).where(
                SyncOutbox.note_id == local_note_id,
                SyncOutbox.status.in_([STATUS_PENDING, STATUS_FAILED]),
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.status = STATUS_DONE
        row.last_error = "conflict_resolved_last_write_wins"
        row.updated_at = _now()
        session.add(row)


def _has_pending_note_ops(session, local_note_id: str) -> bool:
    count = (
        session.execute(
            select(func.count(SyncOutbox.id)).where(
                SyncOutbox.note_id == local_note_id,
                SyncOutbox.status.in_([STATUS_PENDING, STATUS_FAILED]),
            )
        ).scalar_one()
        or 0
    )
    return count > 0


def _get_remote_note_id(session, local_note_id: str) -> Optional[str]:
    row = session.get(SyncNoteMap, local_note_id)
    return row.remote_note_id if row else None


def _get_local_note_id(session, remote_note_id: str) -> Optional[str]:
    row = (
        session.execute(select(SyncNoteMap).where(SyncNoteMap.remote_note_id == remote_note_id))
        .scalars()
        .first()
    )
    return row.local_note_id if row else None


def _set_note_map(session, local_note_id: str, remote_note_id: str) -> None:
    row = session.get(SyncNoteMap, local_note_id)
    if row is None:
        row = SyncNoteMap(local_note_id=local_note_id, remote_note_id=remote_note_id)
    else:
        row.remote_note_id = remote_note_id
    row.updated_at = _now()
    session.add(row)


def _operation_belongs_to_user(
    session,
    item: SyncOutbox,
    payload: Dict[str, Any],
    user_id: str,
) -> bool:
    if item.user_id:
        return item.user_id == user_id

    note_ids: Set[str] = set()
    for key in ("localNoteId", "noteId", "fromId", "toId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            note_ids.add(value)
    if item.note_id:
        note_ids.add(item.note_id)

    if item.op_type == OP_COMMIT:
        draft = payload.get("draft") or []
        if isinstance(draft, list):
            for action in draft:
                if not isinstance(action, dict):
                    continue
                for key in ("noteId", "fromId", "toId"):
                    value = action.get(key)
                    if isinstance(value, str) and value:
                        note_ids.add(value)

    if not note_ids:
        return False

    for note_id in note_ids:
        note = session.get(Note, note_id)
        if note and note.user_id not in {None, user_id}:
            return False
    return True
