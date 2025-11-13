from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, HTMLResponse, StreamingResponse

from app.db.models import FileAsset
from app.db.session import get_session
from app.services.files import PAGES_DIR, _render_pdf_page

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


@router.get("/files/{file_id}/doc.html", response_class=HTMLResponse)
def download_doc_html(file_id: str):
    asset = _fetch_asset(file_id)
    if not asset.path_doc_html:
        raise HTTPException(status_code=404, detail="Document preview not available for this file")
    path = Path(asset.path_doc_html)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document preview file is missing on disk")
    content = path.read_text(encoding="utf-8")
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")


@router.get("/files/{file_id}/waveform")
def download_waveform(file_id: str):
    asset = _fetch_asset(file_id)
    if not asset.path_waveform:
        raise HTTPException(status_code=404, detail="Waveform not available for this file")
    path = Path(asset.path_waveform)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Waveform file is missing on disk")
    return Response(content=path.read_text(encoding="utf-8"), media_type="application/json")


@router.get("/files/{file_id}/stream")
def stream_media(file_id: str, request: Request):
    asset = _fetch_asset(file_id)
    path = Path(asset.path_original)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original file is missing on disk")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    
    # OVC: audio - нормализуем MIME-тип для WebM с codecs
    media_type = asset.mime
    if media_type and "webm" in media_type.lower() and "codecs" in media_type:
        # Для стриминга используем базовый тип, браузер сам определит codec
        media_type = "audio/webm"
    
    if range_header:
        start, end = _parse_range(range_header, file_size)
        chunk_size = 1024 * 64
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Type": media_type,
        }

        def iter_file():
            with path.open("rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(iter_file(), status_code=206, headers=headers, media_type=media_type)

    return FileResponse(path, media_type=media_type, filename=asset.filename)


@router.get("/files/{file_id}/page/{page_num}")
def get_pdf_page(file_id: str, page_num: int, scale: float = Query(1.0, ge=0.5, le=2.0)):
    """OVC: pdf - получение страницы PDF в виде изображения."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        asset = _fetch_asset(file_id)
        if asset.kind != "pdf":
            raise HTTPException(status_code=400, detail="File is not a PDF")
        if not asset.pages or page_num < 1 or page_num > asset.pages:
            raise HTTPException(status_code=404, detail=f"Page {page_num} not found (PDF has {asset.pages or 0} pages)")
        
        # Проверяем кэш
        cache_dir = PAGES_DIR / file_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        scale_key = int(scale * 100)
        cache_path = cache_dir / f"{page_num}_{scale_key}.webp"
        
        if cache_path.exists():
            logger.info(f"Serving cached PDF page {page_num} for {file_id}")
            return FileResponse(cache_path, media_type="image/webp")
        
        # Читаем оригинальный файл и рендерим страницу
        original_path = Path(asset.path_original)
        if not original_path.exists():
            raise HTTPException(status_code=404, detail="Original file is missing on disk")
        
        with original_path.open("rb") as f:
            pdf_data = f.read()
        
        logger.info(f"Rendering PDF page {page_num} for {file_id} (scale={scale})")
        # Проверяем доступность библиотек перед рендерингом
        from app.services.files import HAS_PYMUPDF, HAS_PDF2IMAGE
        if not HAS_PYMUPDF and not HAS_PDF2IMAGE:
            logger.error(f"PDF rendering libraries not available (PyMuPDF: {HAS_PYMUPDF}, pdf2image: {HAS_PDF2IMAGE})")
            raise HTTPException(
                status_code=503,
                detail=f"PDF rendering not available. PyMuPDF: {HAS_PYMUPDF}, pdf2image: {HAS_PDF2IMAGE}. Please install pymupdf: pip install pymupdf"
            )
        
        page_image = _render_pdf_page(pdf_data, page_num, scale)
        if not page_image:
            logger.error(f"Failed to render PDF page {page_num} for {file_id} - render function returned None")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to render PDF page {page_num}. Libraries available: PyMuPDF={HAS_PYMUPDF}, pdf2image={HAS_PDF2IMAGE}"
            )
        
        # Сохраняем в кэш
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as f:
            f.write(page_image)
        
        logger.info(f"Successfully rendered and cached PDF page {page_num} for {file_id}")
        return Response(content=page_image, media_type="image/webp")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rendering PDF page {page_num} for {file_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    if not range_header.startswith("bytes="):
        return 0, file_size - 1
    range_values = range_header.replace("bytes=", "").split("-", 1)
    start = int(range_values[0]) if range_values[0] else 0
    end = int(range_values[1]) if len(range_values) > 1 and range_values[1] else file_size - 1
    start = max(0, start)
    end = min(file_size - 1, end)
    if start > end:
        start = 0
    return start, end
