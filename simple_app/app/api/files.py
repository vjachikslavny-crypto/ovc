from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import FileResponse, Response, HTMLResponse, StreamingResponse, JSONResponse

from app.db.models import FileAsset
from app.db.session import get_session
from app.core.security import get_current_user, get_current_user_or_refresh
from app.models.user import User
from app.services.files import (
    EXCEL_WINDOW_LIMIT,
    PAGES_DIR,
    MAX_CODE_LINES,
    CODE_PREVIEW_LINES,
    MARKDOWN_PREVIEW_MAX_BYTES,
    count_file_lines,
    read_code_segment,
    prepare_code_bytes,
    read_markdown_preview,
    _get_markdown_file_path,
    _get_code_file_path,
    _iter_sheet_csv,
    _load_excel_summary,
    _read_excel_window,
    _render_pdf_page,
)

router = APIRouter(tags=["files"])


def _fetch_asset(file_id: str, user: User) -> FileAsset:
    with get_session() as session:
        asset = session.get(FileAsset, file_id)
        if not asset:
            raise HTTPException(status_code=404, detail="File not found")
        if asset.user_id is None:
            asset.user_id = user.id
            session.add(asset)
            session.flush()
        if asset.user_id != user.id:
            raise HTTPException(status_code=404, detail="File not found")
        return asset


@router.get("/files/{file_id}/original")
def download_original(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    path = Path(asset.path_original)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original file is missing on disk")
    return FileResponse(path, media_type=asset.mime, filename=asset.filename)


@router.get("/files/{file_id}/preview")
def download_preview(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if not asset.path_preview:
        raise HTTPException(status_code=404, detail="Preview not available for this file")
    path = Path(asset.path_preview)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview file is missing on disk")
    media_type = "image/webp" if path.suffix.lower() == ".webp" else asset.mime
    return FileResponse(path, media_type=media_type, filename=f"{asset.id}{path.suffix}")


@router.get("/files/{file_id}/doc.html", response_class=HTMLResponse)
def download_doc_html(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if not asset.path_doc_html:
        raise HTTPException(status_code=404, detail="Document preview not available for this file")
    path = Path(asset.path_doc_html)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document preview file is missing on disk")
    content = path.read_text(encoding="utf-8")
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")


@router.get("/files/{file_id}/slides.json")
def slides_metadata(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "pptx" or not asset.path_slides_json:
        raise HTTPException(status_code=404, detail="Slides metadata unavailable")
    path = Path(asset.path_slides_json)
    if not path.exists():
        return JSONResponse(status_code=202, content={"status": "processing"})
    return FileResponse(path, media_type="application/json")


@router.get("/files/{file_id}/slide/{slide_index}")
def slide_image(file_id: str, slide_index: int, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "pptx":
        raise HTTPException(status_code=400, detail="File is not a PPTX")
    if slide_index < 1:
        raise HTTPException(status_code=400, detail="Invalid slide index")
    if asset.path_slides_dir:
        slides_dir = Path(asset.path_slides_dir)
    else:
        slides_dir = Path(asset.path_slides_json).parent if asset.path_slides_json else Path()
    slide_path = slides_dir / f"{slide_index}.webp"
    if not slide_path.exists():
        raise HTTPException(status_code=404, detail="Slide not found")
    return FileResponse(slide_path, media_type="image/webp")


@router.get("/files/{file_id}/video/source")
def video_source(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "video":
        raise HTTPException(status_code=400, detail="File is not a video")
    path = Path(asset.path_video_original or asset.path_original)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file is missing on disk")
    media_type = asset.video_mime or asset.mime or "video/mp4"
    return FileResponse(path, media_type=media_type, filename=asset.filename)


@router.get("/files/{file_id}/video/poster.webp")
def video_poster(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "video" or not asset.path_video_poster:
        raise HTTPException(status_code=404, detail="Poster not available for this video")
    path = Path(asset.path_video_poster)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Poster file is missing on disk")
    return FileResponse(path, media_type="image/webp")


@router.get("/files/{file_id}/code/meta")
def code_meta(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "code":
        raise HTTPException(status_code=400, detail="File is not code")
    language = asset.code_language or "plaintext"
    line_count = asset.code_line_count
    if line_count is None:
        path = _get_code_file_path(asset)
        line_count = count_file_lines(path)
        with get_session() as session:
            db_asset = session.get(FileAsset, asset.id)
            if db_asset:
                db_asset.code_line_count = line_count
                if not db_asset.code_language:
                    db_asset.code_language = language
                session.commit()
    return {
        "filename": asset.filename,
        "language": language,
        "sizeBytes": asset.size,
        "lineCount": line_count,
    }


@router.get("/files/{file_id}/code/preview")
def code_preview(
    file_id: str,
    max_lines: int = Query(CODE_PREVIEW_LINES, ge=1, le=MAX_CODE_LINES),
    current_user: User = Depends(get_current_user_or_refresh),
):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "code":
        raise HTTPException(status_code=400, detail="File is not code")
    requested = max(1, min(max_lines, MAX_CODE_LINES))
    text, truncated = read_code_segment(asset, 0, requested)
    body, extra_headers = prepare_code_bytes(text, asset)
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    if truncated:
        headers["X-OVC-Code-Truncated"] = "true"
    headers.update(extra_headers)
    return Response(content=body, media_type="text/plain; charset=utf-8", headers=headers)


@router.get("/files/{file_id}/code/raw")
def code_raw(
    file_id: str,
    start: int = Query(0, ge=0),
    max_lines: int = Query(MAX_CODE_LINES, ge=1),
    current_user: User = Depends(get_current_user_or_refresh),
):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "code":
        raise HTTPException(status_code=400, detail="File is not code")
    requested = max(1, min(max_lines, MAX_CODE_LINES))
    text, truncated = read_code_segment(asset, start, requested)
    body, extra_headers = prepare_code_bytes(text, asset)
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    if truncated:
        headers["X-OVC-Code-Truncated"] = "true"
    headers.update(extra_headers)
    return Response(content=body, media_type="text/plain; charset=utf-8", headers=headers)


@router.get("/files/{file_id}/md/preview")
def markdown_preview(
    file_id: str,
    max_bytes: int = Query(MARKDOWN_PREVIEW_MAX_BYTES, ge=1),
    current_user: User = Depends(get_current_user_or_refresh),
):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "markdown":
        raise HTTPException(status_code=400, detail="File is not markdown")
    limit = max(1, min(max_bytes, MARKDOWN_PREVIEW_MAX_BYTES))
    text, truncated = read_markdown_preview(asset, limit)
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    headers["X-OVC-MD-Truncated"] = "true" if truncated else "false"
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)


@router.get("/files/{file_id}/md/raw")
def markdown_raw(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind != "markdown":
        raise HTTPException(status_code=400, detail="File is not markdown")
    path = _get_markdown_file_path(asset)
    text = path.read_text(encoding="utf-8", errors="replace")
    return Response(content=text, media_type="text/plain; charset=utf-8")


@router.get("/files/{file_id}/excel/summary.json")
def excel_summary(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind not in {"xlsx", "xls", "csv"}:
        raise HTTPException(status_code=400, detail="File is not a table")
    summary = _load_excel_summary(asset)
    return JSONResponse(summary)


@router.get("/files/{file_id}/excel/sheet/{sheet_name}.json")
def excel_window(
    file_id: str,
    sheet_name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=EXCEL_WINDOW_LIMIT),
    current_user: User = Depends(get_current_user_or_refresh),
):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind not in {"xlsx", "xls", "csv"}:
        raise HTTPException(status_code=400, detail="File is not a table")
    window = _read_excel_window(asset, sheet_name, offset, limit)
    return JSONResponse(window)


@router.get("/files/{file_id}/excel/sheet/{sheet_name}.csv")
def excel_sheet_csv(file_id: str, sheet_name: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if asset.kind not in {"xlsx", "xls", "csv"}:
        raise HTTPException(status_code=400, detail="File is not a table")
    return _iter_sheet_csv(asset, sheet_name)


@router.get("/files/{file_id}/excel/charts.json")
def excel_charts_meta(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    """Возвращает метаданные диаграмм Excel (аналогично slides.json для PPTX).
    
    Если есть excel_charts_pages_keep (ручной выбор страниц), возвращает только выбранные страницы.
    Иначе возвращает автоматически выбранные страницы.
    """
    from app.services.files import _excel_charts_json_path, _excel_chart_sheets_json_path
    
    asset = _fetch_asset(file_id, current_user)
    if asset.kind not in {"xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="File is not an Excel file")
    
    # Загружаем базовые метаданные
    charts_json_path = Path(asset.path_excel_charts_json) if asset.path_excel_charts_json else None
    if not charts_json_path or not charts_json_path.exists():
        # Проверяем потенциальный путь
        potential_path = _excel_charts_json_path(file_id)
        if potential_path.exists():
            charts_json_path = potential_path
        else:
            raise HTTPException(status_code=404, detail="Charts metadata not available")
    
    with charts_json_path.open('r', encoding='utf-8') as f:
        meta = json.load(f)
    
    # Если есть ручной выбор страниц, фильтруем только выбранные
    if asset.excel_charts_pages_keep:
        try:
            pages_keep = json.loads(asset.excel_charts_pages_keep)
            if isinstance(pages_keep, list) and pages_keep:
                # Фильтруем charts, оставляя только те, чья страница в списке выбранных
                original_charts = meta.get("charts", [])
                filtered_charts = [
                    chart for chart in original_charts
                    if chart.get("page") in pages_keep
                ]
                meta["charts"] = filtered_charts
                meta["count"] = len(filtered_charts)
                meta["mode"] = "manual"
                meta["pages"] = sorted(pages_keep)
        except Exception as e:
            # Если ошибка парсинга - используем автоматический выбор
            pass
    
    return JSONResponse(meta)


@router.get("/files/{file_id}/excel/charts/sheets.json")
def excel_charts_sheets_meta(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    """Возвращает информацию о листах, содержащих диаграммы (структурное обнаружение)."""
    from app.services.files import _excel_chart_sheets_json_path
    
    asset = _fetch_asset(file_id, current_user)
    if asset.kind not in {"xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="File is not an Excel file")
    
    # Проверяем путь из БД
    sheets_json_path = Path(asset.path_excel_chart_sheets_json) if asset.path_excel_chart_sheets_json else None
    if not sheets_json_path or not sheets_json_path.exists():
        # Проверяем потенциальный путь
        potential_path = _excel_chart_sheets_json_path(file_id)
        if potential_path.exists():
            sheets_json_path = potential_path
        else:
            # Возвращаем пустой результат
            return JSONResponse({"hasCharts": False, "sheets": []})
    
    with sheets_json_path.open('r', encoding='utf-8') as f:
        return JSONResponse(json.load(f))


@router.get("/files/{file_id}/excel/charts-anchors.json")
def excel_charts_anchors_meta(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    """Возвращает якоря диаграмм (DrawingML anchors) для точного вырезания."""
    from app.services.files import _excel_chart_anchors_json_path
    
    asset = _fetch_asset(file_id, current_user)
    if asset.kind not in {"xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="File is not an Excel file")
    
    # Проверяем потенциальный путь (не храним в БД, используем конвенцию)
    anchors_json_path = _excel_chart_anchors_json_path(file_id)
    if not anchors_json_path.exists():
        # Возвращаем пустой результат
        return JSONResponse({"sheets": []})
    
    with anchors_json_path.open('r', encoding='utf-8') as f:
        return JSONResponse(json.load(f))


@router.post("/files/{file_id}/excel/charts/pages")
async def save_excel_charts_pages(
    file_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Сохраняет ручной выбор страниц диаграмм пользователем."""
    from app.db.session import get_session
    from app.db.models import FileAsset
    
    asset = _fetch_asset(file_id, current_user)
    if asset.kind not in {"xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="File is not an Excel file")
    
    try:
        body = await request.json()
        if not isinstance(body, dict) or "keep" not in body:
            raise HTTPException(status_code=400, detail="Expected JSON body with 'keep' array")
        
        pages_keep = body["keep"]
        if not isinstance(pages_keep, list):
            raise HTTPException(status_code=400, detail="'keep' must be an array")
        
        # Валидируем, что все страницы - целые числа
        try:
            pages_keep = [int(p) for p in pages_keep]
            pages_keep = sorted(set(pages_keep))  # Убираем дубликаты и сортируем
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="All page numbers must be integers")
        
        # Сохраняем в БД
        with get_session() as session:
            db_asset = session.get(FileAsset, file_id)
            if not db_asset:
                raise HTTPException(status_code=404, detail="File not found")
            if db_asset.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="File not found")
            
            db_asset.excel_charts_pages_keep = json.dumps(pages_keep)
            session.commit()
        
        return JSONResponse({"success": True, "pages": pages_keep})
    
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error saving chart pages selection for {file_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/files/{file_id}/excel/chart/{chart_index}")
def excel_chart_image(file_id: str, chart_index: int, current_user: User = Depends(get_current_user_or_refresh)):
    """Возвращает изображение диаграммы Excel по индексу (аналогично slide/{index} для PPTX)."""
    asset = _fetch_asset(file_id, current_user)
    if asset.kind not in {"xlsx", "xls"}:
        raise HTTPException(status_code=400, detail="File is not an Excel file")
    if not asset.path_excel_charts_dir:
        raise HTTPException(status_code=404, detail="Charts directory not available")
    charts_dir = Path(asset.path_excel_charts_dir)
    if not charts_dir.exists():
        raise HTTPException(status_code=404, detail="Charts directory is missing on disk")
    if chart_index < 1:
        raise HTTPException(status_code=400, detail="Invalid chart index")
    chart_path = charts_dir / f"{chart_index}.webp"
    if not chart_path.exists():
        raise HTTPException(status_code=404, detail=f"Chart {chart_index} not found")
    return FileResponse(chart_path, media_type="image/webp", filename=f"chart_{chart_index}.webp")


@router.get("/files/{file_id}/waveform")
def download_waveform(file_id: str, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
    if not asset.path_waveform:
        raise HTTPException(status_code=404, detail="Waveform not available for this file")
    path = Path(asset.path_waveform)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Waveform file is missing on disk")
    return Response(content=path.read_text(encoding="utf-8"), media_type="application/json")


@router.get("/files/{file_id}/stream")
def stream_media(file_id: str, request: Request, current_user: User = Depends(get_current_user_or_refresh)):
    asset = _fetch_asset(file_id, current_user)
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
def get_pdf_page(
    file_id: str,
    page_num: int,
    scale: float = Query(1.0, ge=0.5, le=2.0),
    current_user: User = Depends(get_current_user_or_refresh),
):
    """OVC: pdf - получение страницы PDF в виде изображения."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        asset = _fetch_asset(file_id, current_user)
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
