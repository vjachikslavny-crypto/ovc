from __future__ import annotations

import hashlib
import io
import json
from typing import List

from fastapi import APIRouter, Depends, Request, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.security import get_bearer_token, get_current_user
from app.core.ownership import get_owned_note
from app.models.user import User
from app.db.session import get_session
from app.db.models import SyncChangeLog, FileAsset, Note
from fastapi.responses import FileResponse
from app.services import files as file_service
from app.services.sync_engine import get_sync_status, trigger_sync_now
from app.services.sync_protocol import (SyncOperation, identity, receipt, store_receipt,
    apply_note_operation, bootstrap_log, record_file_change, file_payload)

router = APIRouter(tags=['sync'])


def sync_user(request: Request, user: User = Depends(get_current_user)):
    # The dev identity is never a remote authentication credential.
    if settings.auth_mode == 'none' or getattr(request.state, 'auth_context', '') not in {'local-user', 'supabase-user'}:
        raise HTTPException(403, 'Sync requires authenticated user context')
    return user


@router.get('/sync/status')
def sync_status(current_user: User = Depends(get_current_user)):
    return get_sync_status(user_id=current_user.id)


@router.post('/sync/trigger')
def sync_trigger(request: Request, current_user: User = Depends(sync_user)):
    return trigger_sync_now(access_token=get_bearer_token(request), user_id=current_user.id)


@router.get('/sync/hello')
def sync_hello(request: Request, current_user: User = Depends(sync_user)):
    with get_session() as session:
        context = getattr(request.state, 'auth_context', '')
        if context not in {'local-user', 'supabase-user'}:
            raise HTTPException(403, 'Sync requires a real authenticated identity')
        return {'protocol_version': 1, 'server_id': identity(session, 'server_id'), 'user_id': current_user.id,
                'auth_context': context, 'auth_subject': current_user.supabase_id if context == 'supabase-user' else current_user.id}


@router.get('/sync/files/{file_id}/original')
def sync_original(file_id: str, current_user: User = Depends(sync_user)):
    # Historical events may reference files whose parent has since been deleted.
    # They remain owner-scoped and are needed to replay a page before its tombstone.
    with get_session() as session:
        asset = session.get(FileAsset, file_id)
        parent = session.get(Note, asset.note_id) if asset and asset.note_id else None
        if not asset or asset.user_id != current_user.id or (asset.note_id and (not parent or parent.user_id != current_user.id)):
            raise HTTPException(404, 'File not found')
        return FileResponse(asset.path_original, media_type=asset.mime, filename=asset.filename)


class PushRequest(BaseModel):
    # Validate individually so one invalid operation cannot undo an acknowledged peer.
    operations: List[dict] = Field(min_length=1, max_length=100)


@router.post('/sync/push')
def sync_push(body: PushRequest, current_user: User = Depends(sync_user)):
    results = []
    for raw in body.operations:
        try:
            op = SyncOperation.model_validate(raw)
            with get_session(immediate=True) as session:
                result = apply_note_operation(session, current_user.id, op)
            results.append(result)
        except (ValidationError, ValueError, KeyError, TypeError):
            results.append({'op_id': raw.get('op_id'), 'status': 'failed_permanent', 'error': 'Invalid operation schema or protocol'})
        except HTTPException as exc:
            status = 'auth_required' if exc.status_code == 401 else 'retry' if exc.status_code >= 500 or exc.status_code in (408, 429) else 'failed_permanent'
            results.append({'op_id': raw.get('op_id'), 'status': status, 'error': str(exc.detail), 'http_status': exc.status_code})
        except OperationalError:
            results.append({'op_id': raw.get('op_id'), 'status': 'retry', 'error': 'Database temporarily unavailable'})
    return {'results': results}


@router.get('/sync/pull')
def sync_pull(cursor: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
              current_user: User = Depends(sync_user)):
    with get_session(immediate=True) as session:
        if cursor == 0:
            bootstrap_log(session, current_user.id)
        rows = session.execute(select(SyncChangeLog).where(SyncChangeLog.protocol_version == 1,
            SyncChangeLog.user_id == current_user.id, SyncChangeLog.sequence > cursor)
            .order_by(SyncChangeLog.sequence).limit(limit + 1)).scalars().all()
        page = rows[:limit]
        return {'protocol_version': 1, 'server_id': identity(session, 'server_id'),
            'changes': [{'sequence': r.sequence, 'entity_type': r.entity_type, 'entity_id': r.entity_id,
                'revision': r.server_version, 'deleted': r.deleted, 'payload': json.loads(r.payload_json)} for r in page],
            'next_cursor': page[-1].sequence if page else cursor, 'has_more': len(rows) > limit}


@router.post('/sync/files')
async def sync_file(operation: str = Form(...), file: UploadFile = File(...),
                    current_user: User = Depends(sync_user)):
    try:
        op = SyncOperation.model_validate_json(operation)
    except ValidationError:
        raise HTTPException(422, 'Invalid operation schema or protocol')
    if op.entity_type != 'file' or op.operation_type != 'upload' or op.entity_remote_id or op.base_revision is not None:
        raise HTTPException(422, 'Expected a new file upload operation')
    from app.services.runtime import run_blocking
    return await run_blocking(_store_sync_file, op, file, current_user.id)


def _store_sync_file(op, file, user_id):
    from app.services.upload_pipeline import prepare_upload, cleanup_asset
    from app.services.runtime import check_cancelled
    payload = op.payload
    digest = hashlib.sha256()
    size = 0
    while True:
        check_cancelled()
        data = file.file.read(1024 * 1024)
        if not data:
            break
        size += len(data)
        if size > settings.max_file_bytes:
            raise HTTPException(413, 'File too large')
        digest.update(data)
    if (digest.hexdigest() != payload.get('sha256') or size != payload.get('size')
            or file.filename != payload.get('filename') or file.content_type != payload.get('mime')):
        raise HTTPException(422, 'File metadata/checksum mismatch')
    note_id = payload.get('noteId')
    with get_session() as session:
        previous, _ = receipt(session, user_id, op)
        if previous is not None:
            return previous
        if note_id:
            get_owned_note(session, note_id, user_id)
    stored = prepare_upload(file, note_id, user_id, upload_op_id=str(op.op_id))
    committed = False
    try:
        check_cancelled()
        with get_session(immediate=True) as session:
            previous, fingerprint = receipt(session, user_id, op)
            if previous is not None:
                return previous
            if note_id:
                get_owned_note(session, note_id, user_id)
            session.add(stored.asset)
            session.flush()
            record_file_change(session, stored.asset)
            result = {'op_id': str(op.op_id), 'status': 'applied', 'entity_remote_id': stored.asset.id,
                      'revision': 1, 'snapshot': file_payload(stored.asset)}
            store_receipt(session, user_id, op, fingerprint, result)
        committed = True
        return result
    finally:
        if not committed:
            cleanup_asset(stored.asset.id)
