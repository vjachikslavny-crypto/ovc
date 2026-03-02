from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, Request, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.db.models import FileAsset, Note
from app.db.session import get_session
from app.services import files as file_service
from app.core.security import get_current_user
from app.models.user import User
from app.services.audit import log_event
from app.services.sync_engine import OP_UPLOAD_FILE, enqueue_sync_operation

# OVC: video - увеличиваем лимит размера файла
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB

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


async def _store_uploads(
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

    with get_session() as session:
        try:
            if note_id:
                note = session.get(Note, note_id)
                if not note:
                    raise HTTPException(status_code=404, detail="Note not found")
                if note.user_id is None:
                    note.user_id = user.id
                    session.add(note)
                    session.flush()
                if note.user_id != user.id:
                    raise HTTPException(status_code=404, detail="Note not found")

            for upload in uploads:
                existing_asset = None
                if upload_op_id:
                    # Idempotency guard for desktop retries: same op id should not create duplicate files.
                    existing_asset = (
                        session.query(FileAsset)
                        .filter(
                            FileAsset.user_id == user.id,
                            FileAsset.note_id == note_id,
                            FileAsset.upload_op_id == upload_op_id,
                        )
                        .first()
                    )

                if existing_asset:
                    asset = existing_asset
                    block = file_service._build_block(asset)
                else:
                    stored = await file_service.save_upload(
                        session,
                        upload,
                        note_id,
                        user.id,
                        upload_op_id=upload_op_id,
                    )
                    asset = stored.asset
                    block = stored.block

                original_url = f"/files/{asset.id}/original"
                preview_url = f"/files/{asset.id}/preview" if asset.path_preview else None
                if asset.kind == "video":
                    original_url = f"/files/{asset.id}/video/source"
                    preview_url = f"/files/{asset.id}/video/poster.webp" if asset.path_video_poster else preview_url
                response_blocks.append(block)
                response_files.append(
                    UploadedFilePayload(
                        id=asset.id,
                        kind=asset.kind,
                        mime=asset.mime,
                        size=asset.size,
                        filename=asset.filename,
                        originalUrl=original_url,
                        previewUrl=preview_url,
                    )
                )
                log_event(
                    session,
                    "FILE_UPLOAD",
                    user_id=user.id,
                    request=request,
                    metadata={"file_id": asset.id, "kind": asset.kind},
                )
                if note_id:
                    enqueue_sync_operation(
                        session,
                        OP_UPLOAD_FILE,
                        {
                            "localNoteId": note_id,
                            "fileAssetId": asset.id,
                            "filePath": asset.path_original,
                            "filename": asset.filename,
                            "mime": asset.mime,
                        },
                        note_id=note_id,
                        user_id=user.id,
                    )

            session.commit()
        except HTTPException:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return UploadResponse(noteId=note_id, blocks=response_blocks, files=response_files)


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
    await file.read()
    return PlainTextResponse("Voice transcription not configured")
