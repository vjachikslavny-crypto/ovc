from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.db.models import FileAsset
from app.db.session import get_session

router = APIRouter(tags=["files"])


def _fetch_asset(file_id: str) -> FileAsset:
    with get_session() as session:
        asset = session.get(FileAsset, file_id)
        if not asset:
            raise HTTPException(status_code=404, detail="File not found")
        return asset


@router.get("/files/{file_id}/original")
def download_original(file_id: str):
    asset = _fetch_asset(file_id)
    path = Path(asset.path_original)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original file is missing on disk")
    return FileResponse(path, media_type=asset.mime, filename=asset.filename)


@router.get("/files/{file_id}/preview")
def download_preview(file_id: str):
    asset = _fetch_asset(file_id)
    if not asset.path_preview:
        raise HTTPException(status_code=404, detail="Preview not available for this file")
    path = Path(asset.path_preview)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview file is missing on disk")
    media_type = "image/webp" if path.suffix.lower() == ".webp" else asset.mime
    return FileResponse(path, media_type=media_type, filename=f"{asset.id}{path.suffix}")
