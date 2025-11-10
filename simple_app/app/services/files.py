from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.block_models import DocBlock, DocData, DocMeta, ImageBlock, ImageData, dump_block
from app.db.models import FileAsset, generate_uuid

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


PROJECT_ROOT = Path(__file__).resolve().parents[4] if len(Path(__file__).resolve().parents) >= 5 else Path.cwd()
UPLOAD_ROOT = PROJECT_ROOT / "data" / "uploads"
ORIGINAL_DIR = UPLOAD_ROOT / "original"
PREVIEW_DIR = UPLOAD_ROOT / "preview"

for directory in (ORIGINAL_DIR, PREVIEW_DIR):
    directory.mkdir(parents=True, exist_ok=True)


IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
PDF_MIME_TYPES = {"application/pdf"}

IMAGE_MAX_BYTES = 15 * 1024 * 1024
PDF_MAX_BYTES = 50 * 1024 * 1024


class FileMetadata(BaseModel):
    kind: str
    mime: str
    extension: str
    max_bytes: int


def _guess_extension(filename: str, mime: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(mime)
    return guessed or ".bin"


def _classify_file(upload: UploadFile) -> FileMetadata:
    filename = upload.filename or ""
    mime = (upload.content_type or "").lower()
    if not mime:
        guessed, _ = mimetypes.guess_type(filename)
        mime = (guessed or "application/octet-stream").lower()

    if mime in IMAGE_MIME_TYPES or filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return FileMetadata(kind="image", mime=mime, extension=_guess_extension(filename, mime), max_bytes=IMAGE_MAX_BYTES)
    if mime in PDF_MIME_TYPES or filename.lower().endswith(".pdf"):
        return FileMetadata(kind="pdf", mime="application/pdf", extension=".pdf", max_bytes=PDF_MAX_BYTES)

    raise HTTPException(status_code=415, detail="Unsupported file type for this prototype (image/pdf only).")


def _write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)


def _generate_image_preview(data: bytes) -> Tuple[bytes, int, int]:
    buffer = BytesIO(data)
    with Image.open(buffer) as img:
        img = ImageOps.exif_transpose(img)
        width, height = img.size
        preview = img.copy()
        preview.thumbnail((1600, 1600))
        out = BytesIO()
        preview.save(out, format="WEBP", quality=85)
        preview_bytes = out.getvalue()
    return preview_bytes, width, height


def _generate_pdf_preview(file_id: str, pages: Optional[int]) -> bytes:
    width, height = 1200, 800
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    title = "PDF Document"
    subtitle = f"{pages or '?'} pages"
    draw.text((width // 2 - 120, height // 2 - 40), title, fill="#0f172a", font=font)
    draw.text((width // 2 - 80, height // 2 + 10), subtitle, fill="#475569", font=font)
    out = BytesIO()
    image.save(out, format="WEBP", quality=85)
    return out.getvalue()


def _pdf_page_count(data: bytes) -> Optional[int]:
    if PdfReader is None:
        return None
    try:
        reader = PdfReader(BytesIO(data))
        return len(reader.pages)
    except Exception:
        return None


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_url(file_id: str, variant: str) -> str:
    return f"/files/{file_id}/{variant}"


def _build_block(asset: FileAsset) -> dict:
    if asset.kind == "image":
        block = ImageBlock(
            type="image",
            id=generate_uuid(),
            data=ImageData(
                src=_file_url(asset.id, "preview") if asset.path_preview else _file_url(asset.id, "original"),
                full=_file_url(asset.id, "original"),
                alt=asset.filename,
                w=asset.width,
                h=asset.height,
            ),
        )
        return dump_block(block)

    if asset.kind == "pdf":
        # Извлекаем имя файла без расширения для title
        filename_without_ext = Path(asset.filename).stem if asset.filename else None
        doc_data = DocData(
            kind="pdf",
            src=_file_url(asset.id, "original"),
            title=filename_without_ext or "PDF-документ",
            preview=_file_url(asset.id, "preview") if asset.path_preview else None,
            meta=DocMeta(pages=asset.pages, slides=None, size=asset.size),
        )
        block = DocBlock(type="doc", id=generate_uuid(), data=doc_data)
        return dump_block(block)

    raise HTTPException(status_code=500, detail=f"Unknown asset kind: {asset.kind}")


@dataclass
class StoredAsset:
    asset: FileAsset
    block: dict


async def save_upload(session: Session, upload: UploadFile, note_id: Optional[str]) -> StoredAsset:
    meta = _classify_file(upload)
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > meta.max_bytes:
        raise HTTPException(status_code=413, detail="File too large for this prototype")

    file_id = generate_uuid()
    original_name = upload.filename or f"{file_id}{meta.extension}"
    original_path = ORIGINAL_DIR / f"{file_id}{meta.extension}"
    _write_file(original_path, data)

    preview_path = None
    width = height = pages = None

    if meta.kind == "image":
        preview_bytes, width, height = _generate_image_preview(data)
        preview_path = PREVIEW_DIR / f"{file_id}.webp"
        _write_file(preview_path, preview_bytes)
    elif meta.kind == "pdf":
        pages = _pdf_page_count(data)
        preview_bytes = _generate_pdf_preview(file_id, pages)
        preview_path = PREVIEW_DIR / f"{file_id}.webp"
        _write_file(preview_path, preview_bytes)

    asset = FileAsset(
        id=file_id,
        note_id=note_id,
        kind=meta.kind,
        mime=meta.mime,
        filename=original_name,
        size=len(data),
        path_original=str(original_path),
        path_preview=str(preview_path) if preview_path else None,
        hash_sha256=_hash_bytes(data),
        width=width,
        height=height,
        pages=pages,
    )
    session.add(asset)
    session.flush()

    block = _build_block(asset)
    return StoredAsset(asset=asset, block=block)
