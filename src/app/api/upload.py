from __future__ import annotations

from typing import List, Optional
from pathlib import Path
import hashlib

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, Request, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.db.models import FileAsset, Note
from app.db.session import get_session
from app.core.ownership import get_owned_note
from app.services import files as file_service
from app.core.security import get_current_user
from app.models.user import User
from app.services.audit import log_event
from app.services.sync_protocol import lock_stream, record_file_change
from app.services.sync_engine import OP_UPLOAD_FILE, enqueue_sync_operation

router = APIRouter(tags=["files"])


class UploadedFilePayload(BaseModel):
    id: str
    kind: str
    mime: str
    size: int
    filename: str
    original_url: str = Field(alias="originalUrl")
    preview_url: Optional[str] = Field(default=None, alias="previewUrl")

    class Config:
        allow_population_by_field_name = True


class UploadResponse(BaseModel):
    note_id: Optional[str] = Field(default=None, alias="noteId")
    blocks: List[dict]
    files: List[UploadedFilePayload]

    class Config:
        allow_population_by_field_name = True


def _store_uploads_sync(
    note_id: Optional[str],
    uploads: List[UploadFile],
    user: User,
    request: Request,
) -> UploadResponse:
    if not uploads:
        raise HTTPException(status_code=400, detail="No files provided")

    response_blocks: List[dict] = []
    response_files: List[UploadedFilePayload] = []

    upload_op_id = request.headers.get("X-Upload-Op-Id") or request.headers.get("X-Desktop-Op-Id")

    from app.services.upload_pipeline import prepare_upload, cleanup_asset
    from app.services.runtime import check_cancelled
    from app.core.config import settings
    if len(uploads) > settings.max_upload_files:
        raise HTTPException(413, 'Too many files in one request')
    if upload_op_id and (len(upload_op_id) > 128 or any(ord(c) < 32 for c in upload_op_id)):
        raise HTTPException(422, 'Invalid upload operation id')
    with get_session() as session:
        if note_id:
            get_owned_note(session, note_id, user.id)
    prepared = []
    committed = False
    unused = []
    try:
        for i, upload in enumerate(uploads):
            key = (upload_op_id if len(uploads) == 1 else f'{upload_op_id}:{i}') if upload_op_id else None
            with get_session() as session:
                existing = session.query(FileAsset).filter_by(user_id=user.id, note_id=note_id, upload_op_id=key).first() if key else None
            if existing:
                digest = hashlib.sha256()
                size = 0
                upload.file.seek(0)
                for chunk in iter(lambda: upload.file.read(1024 * 1024), b''):
                    check_cancelled()
                    size += len(chunk)
                    if size > settings.max_file_bytes:
                        raise HTTPException(413, 'File exceeds the configured size limit')
                    digest.update(chunk)
                if (size != existing.size or digest.hexdigest() != existing.hash_sha256
                        or Path((upload.filename or '').replace('\\', '/')).name != existing.filename):
                    raise HTTPException(409, 'Upload operation id already used for different content')
                if not Path(existing.path_original).is_file():
                    raise HTTPException(409, 'Previous upload storage is unavailable')
            stored = None if existing else prepare_upload(upload, note_id, user.id, key)
            prepared.append((key, stored, existing))
        check_cancelled()
        with get_session(immediate=True) as session:
            lock_stream(session)
            if note_id:
                get_owned_note(session, note_id, user.id)
            for key, stored, prior in prepared:
                existing_asset = session.query(FileAsset).filter_by(user_id=user.id, note_id=note_id, upload_op_id=key).first() if key else None
                if existing_asset:
                    if stored and (
                            existing_asset.hash_sha256 != stored.asset.hash_sha256 or
                            existing_asset.filename != stored.asset.filename):
                        raise HTTPException(409, 'Upload operation id already used for different content')
                    asset = existing_asset
                    block = file_service._build_block(asset)
                    if stored:
                        unused.append(stored.asset.id)
                else:
                    if stored is None:
                        raise HTTPException(409, 'Upload changed during retry')
                    asset, block = stored.asset, stored.block
                    session.add(asset)
                    session.flush()
                    record_file_change(session, asset)
                original_url = f"/files/{asset.id}/original"
                preview_url = f"/files/{asset.id}/preview" if asset.path_preview else None
                if asset.kind == "video":
                    original_url = f"/files/{asset.id}/video/source"
                    preview_url = f"/files/{asset.id}/video/poster.webp" if asset.path_video_poster else preview_url
                response_blocks.append(block)
                response_files.append(UploadedFilePayload(id=asset.id, kind=asset.kind, mime=asset.mime,
                    size=asset.size, filename=asset.filename, originalUrl=original_url, previewUrl=preview_url))
                log_event(session, 'FILE_UPLOAD', user_id=user.id, request=request,
                          metadata={'file_id':asset.id, 'kind':asset.kind})
                if not existing_asset:
                    enqueue_sync_operation(session, OP_UPLOAD_FILE, {
                        'localNoteId':note_id, 'fileAssetId':asset.id, 'filePath':asset.path_original,
                        'filename':asset.filename, 'mime':asset.mime}, note_id=note_id, user_id=user.id)
        committed = True
    except HTTPException:
        raise
    except Exception:
        import logging
        logging.getLogger(__name__).warning('upload_commit_failed')
        raise HTTPException(500, 'Upload failed') from None
    finally:
        for _, stored, _ in prepared:
            if stored and (not committed or stored.asset.id in unused):
                cleanup_asset(stored.asset.id)

    return UploadResponse(noteId=note_id, blocks=response_blocks, files=response_files)


async def _store_uploads(note_id, uploads, user, request):
    from app.services.runtime import run_for_request
    from app.core.config import settings
    from app.services.rate_limit import limit_operation
    limit_operation('upload', user.id, settings.rate_limit_upload_per_min)
    return await run_for_request(request, _store_uploads_sync, note_id, uploads, user, request)


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    note_id: Optional[str] = Query(default=None, alias="noteId"),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
):
    return await _store_uploads(note_id, files, current_user, request)


@router.post("/upload/audio", response_model=UploadResponse)
async def upload_audio(
    request: Request,
    note_id: Optional[str] = Query(default=None, alias="noteId"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    return await _store_uploads(note_id, [file], current_user, request)


@router.post("/transcribe", response_class=PlainTextResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("audio/"):
        raise HTTPException(status_code=415, detail="Only audio files can be transcribed")
    from app.core.config import settings
    if file.size is not None and file.size > settings.max_file_bytes:
        raise HTTPException(413, "File too large")
    return PlainTextResponse("Voice transcription not configured")
