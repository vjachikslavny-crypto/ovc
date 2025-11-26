from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, Request
from pydantic import BaseModel, Field

from app.db.models import Note
from app.db.session import get_session
from app.services import files as file_service

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


async def _store_uploads(note_id: Optional[str], uploads: List[UploadFile]) -> UploadResponse:
    if not uploads:
        raise HTTPException(status_code=400, detail="No files provided")

    response_blocks: List[dict] = []
    response_files: List[UploadedFilePayload] = []

    with get_session() as session:
        try:
            if note_id:
                note = session.get(Note, note_id)
                if not note:
                    raise HTTPException(status_code=404, detail="Note not found")

            for upload in uploads:
                stored = await file_service.save_upload(session, upload, note_id)
                asset = stored.asset
                original_url = f"/files/{asset.id}/original"
                preview_url = f"/files/{asset.id}/preview" if asset.path_preview else None
                if asset.kind == "video":
                    original_url = f"/files/{asset.id}/video/source"
                    preview_url = f"/files/{asset.id}/video/poster.webp" if asset.path_video_poster else preview_url
                response_blocks.append(stored.block)
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
    note_id: Optional[str] = Query(default=None, alias="noteId"),
    files: List[UploadFile] = File(...),
):
    return await _store_uploads(note_id, files)


@router.post("/upload/audio", response_model=UploadResponse)
async def upload_audio(
    note_id: Optional[str] = Query(default=None, alias="noteId"),
    file: UploadFile = File(...),
):
    return await _store_uploads(note_id, [file])
