from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

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
