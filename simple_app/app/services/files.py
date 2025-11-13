from __future__ import annotations

import hashlib
import mimetypes
import logging
import html as html_module
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
    import bleach
except ImportError:  # pragma: no cover
    bleach = None

try:
    import mammoth
except ImportError:  # pragma: no cover
    mammoth = None

try:
    from striprtf.striprtf import rtf_to_text
except ImportError:  # pragma: no cover
    rtf_to_text = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:  # pragma: no cover
    HAS_PYMUPDF = False
except Exception:
    HAS_PYMUPDF = False

try:
    from pdf2image import convert_from_bytes
    HAS_PDF2IMAGE = True
except ImportError:  # pragma: no cover
    HAS_PDF2IMAGE = False

# OVC: docx - Playwright больше не используется для генерации превью Word файлов
# Превью для Word файлов не генерируется, используется только inline просмотр


PROJECT_ROOT = Path(__file__).resolve().parents[4] if len(Path(__file__).resolve().parents) >= 5 else Path.cwd()
UPLOAD_ROOT = PROJECT_ROOT / "data" / "uploads"
ORIGINAL_DIR = UPLOAD_ROOT / "original"
PREVIEW_DIR = UPLOAD_ROOT / "preview"
PAGES_DIR = UPLOAD_ROOT / "pages"  # OVC: pdf - кэш страниц PDF
DOC_HTML_DIR = UPLOAD_ROOT / "doc_html"

for directory in (ORIGINAL_DIR, PREVIEW_DIR, PAGES_DIR, DOC_HTML_DIR):
    directory.mkdir(parents=True, exist_ok=True)


IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
PDF_MIME_TYPES = {"application/pdf"}
DOCX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
RTF_MIME_TYPES = {"application/rtf", "text/rtf"}

IMAGE_MAX_BYTES = 15 * 1024 * 1024
PDF_MAX_BYTES = 50 * 1024 * 1024
DOC_MAX_BYTES = 30 * 1024 * 1024

ALLOWED_HTML_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "s",
    "a",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "pre",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "img",
    "figure",
    "figcaption",
    "span",
]

ALLOWED_HTML_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    "*": ["class"],
}


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
    if mime in DOCX_MIME_TYPES or filename.lower().endswith(".docx"):
        return FileMetadata(kind="docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", extension=".docx", max_bytes=DOC_MAX_BYTES)
    if mime in RTF_MIME_TYPES or filename.lower().endswith(".rtf"):
        return FileMetadata(kind="rtf", mime="application/rtf", extension=".rtf", max_bytes=DOC_MAX_BYTES)

    raise HTTPException(status_code=415, detail="Unsupported file type for this prototype (image/pdf/docx/rtf only).")


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


def _render_pdf_page(data: bytes, page_num: int, scale: float = 1.0) -> Optional[bytes]:
    """OVC: pdf - рендеринг страницы PDF в изображение."""
    if page_num < 1:
        return None
    
    try:
        # Попытка использовать PyMuPDF (fitz) - самый быстрый вариант
        if HAS_PYMUPDF:
            try:
                doc = fitz.open(stream=data, filetype="pdf")
                if page_num > len(doc):
                    doc.close()
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Page {page_num} out of range (PDF has {len(doc)} pages)")
                    return None
                page = doc[page_num - 1]  # 0-based index
                # PyMuPDF: zoom factor (1.0 = 72 DPI, 2.0 = 144 DPI)
                # Для лучшего качества используем scale * 1.5
                zoom = scale * 1.5
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                # Конвертируем в PNG сначала
                img_data = pix.tobytes("png")
                doc.close()
                # Конвертируем PNG в WEBP
                img = Image.open(BytesIO(img_data))
                out = BytesIO()
                img.save(out, format="WEBP", quality=85, method=6)
                return out.getvalue()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"PyMuPDF render error for page {page_num}: {e}", exc_info=True)
                return None
        
        # Попытка использовать pdf2image
        if HAS_PDF2IMAGE:
            try:
                images = convert_from_bytes(data, first_page=page_num, last_page=page_num, dpi=int(72 * scale))
                if not images:
                    return None
                img = images[0]
                # Масштабируем если нужно
                if scale != 1.0:
                    new_size = (int(img.width * scale), int(img.height * scale))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                out = BytesIO()
                img.save(out, format="WEBP", quality=85)
                return out.getvalue()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"pdf2image render error: {e}", exc_info=True)
                return None
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"PDF render error: {e}", exc_info=True)
        return None
    
    return None


def _generate_pdf_preview(data: bytes, file_id: str, pages: Optional[int]) -> bytes:
    """OVC: pdf - генерация preview для PDF (рендер первой страницы или placeholder)."""
    # Пытаемся отрендерить первую страницу
    try:
        preview_img = _render_pdf_page(data, 1, scale=1.0)
        if preview_img:
            # Масштабируем до разумного размера для preview
            img = Image.open(BytesIO(preview_img))
            img.thumbnail((1200, 1600), Image.Resampling.LANCZOS)
            out = BytesIO()
            img.save(out, format="WEBP", quality=85)
            return out.getvalue()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"PDF preview generation error: {e}", exc_info=True)
    
    # Fallback: placeholder если рендеринг недоступен
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"PDF preview: using placeholder for {file_id} (libraries: PyMuPDF={HAS_PYMUPDF}, pdf2image={HAS_PDF2IMAGE})")
    width, height = 1200, 800
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    title = "PDF Document"
    subtitle = f"{pages or '?'} pages" if pages else "PDF файл"
    # Простой расчет позиции для текста
    try:
        bbox = draw.textbbox((0, 0), title, font=font)
        title_width = bbox[2] - bbox[0]
        title_height = bbox[3] - bbox[1]
    except:
        title_width = len(title) * 20
        title_height = 30
    try:
        bbox_small = draw.textbbox((0, 0), subtitle, font=font)
        subtitle_width = bbox_small[2] - bbox_small[0]
    except:
        subtitle_width = len(subtitle) * 12
    draw.text((width // 2 - title_width // 2, height // 2 - 40), title, fill="#0f172a", font=font)
    draw.text((width // 2 - subtitle_width // 2, height // 2 + 10), subtitle, fill="#475569", font=font)
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


def _sanitize_html_fragment(fragment: str) -> str:
    if bleach is None:  # pragma: no cover
        return html_module.escape(fragment)
    cleaned = bleach.clean(fragment, tags=ALLOWED_HTML_TAGS, attributes=ALLOWED_HTML_ATTRS, strip=True)
    return cleaned


def _write_doc_html(file_id: str, html_fragment: str) -> Path:
    path = DOC_HTML_DIR / f"{file_id}.html"
    path.write_text(html_fragment, encoding="utf-8")
    return path


# OVC: docx - функция генерации превью удалена, т.к. превью для Word файлов не генерируется
# Вместо превью используется информативный бейдж с названием файла и количеством слов


def _convert_docx_to_html(data: bytes) -> tuple[str, Optional[int]]:
    if mammoth is None:
        raise HTTPException(status_code=500, detail="DOCX preview is unavailable (mammoth not installed).")
    result = mammoth.convert_to_html(BytesIO(data))
    html_fragment = result.value or ""
    if bleach is not None:
        text_only = bleach.clean(html_fragment, tags=[], strip=True)
    else:  # pragma: no cover
        text_only = html_module.escape(html_fragment)
    word_count = len(text_only.split())
    return html_fragment, word_count


def _convert_rtf_to_html(data: bytes) -> tuple[str, Optional[int]]:
    if rtf_to_text is None:
        raise HTTPException(status_code=500, detail="RTF preview is unavailable (striprtf not installed).")
    try:
        text = rtf_to_text(data.decode("utf-8", errors="ignore"))
    except Exception:
        text = rtf_to_text(data.decode("latin-1", errors="ignore"))
    paragraphs = [seg.strip() for seg in text.split("\n") if seg.strip()]
    html_parts = []
    for paragraph in paragraphs:
        html_parts.append(f"<p>{html_module.escape(paragraph)}</p>")
    html_fragment = "".join(html_parts)
    word_count = len(text.split())
    return html_fragment, word_count


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
            view="cover",  # OVC: pdf - по умолчанию режим обложки
        )
        block = DocBlock(type="doc", id=generate_uuid(), data=doc_data)
        return dump_block(block)

    if asset.kind in {"docx", "rtf"}:
        filename_without_ext = Path(asset.filename).stem if asset.filename else None
        doc_data = DocData(
            kind="docx" if asset.kind == "docx" else "rtf",
            src=_file_url(asset.id, "original"),
            title=filename_without_ext or asset.filename,
            preview=_file_url(asset.id, "preview") if asset.path_preview else None,
            meta=DocMeta(pages=asset.pages, slides=None, size=asset.size, words=asset.words),
            view="cover",
        )
        block = DocBlock(type="doc", id=generate_uuid(), data=doc_data)
        return dump_block(block)

    raise HTTPException(status_code=500, detail=f"Unknown asset kind: {asset.kind}")


@dataclass
class StoredAsset:
    asset: FileAsset
    block: dict


async def save_upload(session: Session, upload: UploadFile, note_id: Optional[str]) -> StoredAsset:
    logger = logging.getLogger(__name__)  # OVC: docx - определяем logger в начале функции
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
    doc_html_path = None
    width = None
    height = None
    pages = None
    words = None

    if meta.kind == "image":
        preview_bytes, width, height = _generate_image_preview(data)
        preview_path = PREVIEW_DIR / f"{file_id}.webp"
        _write_file(preview_path, preview_bytes)
    elif meta.kind == "pdf":
        pages = _pdf_page_count(data)
        preview_bytes = _generate_pdf_preview(data, file_id, pages)  # OVC: pdf - передаем data для рендеринга
        preview_path = PREVIEW_DIR / f"{file_id}.webp"
        _write_file(preview_path, preview_bytes)
    elif meta.kind in {"docx", "rtf"}:
        try:
            if meta.kind == "docx":
                html_fragment, words = _convert_docx_to_html(data)
            else:
                html_fragment, words = _convert_rtf_to_html(data)
            sanitized = _sanitize_html_fragment(html_fragment)
            doc_html_path = _write_doc_html(file_id, sanitized)
            
            # OVC: docx - не генерируем превью для Word файлов, используем только inline просмотр
            # Превью не создается - будет показан бейдж с типом файла
            preview_path = None
            logger.info(f"Processed {meta.kind} file {file_id}, HTML length: {len(html_fragment)}, words: {words}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing {meta.kind} file: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error processing {meta.kind} file: {str(e)}")

    asset = FileAsset(
        id=file_id,
        note_id=note_id,
        kind=meta.kind,
        mime=meta.mime,
        filename=original_name,
        size=len(data),
        path_original=str(original_path),
        path_preview=str(preview_path) if preview_path else None,
        path_doc_html=str(doc_html_path) if doc_html_path else None,
        hash_sha256=_hash_bytes(data),
        width=width,
        height=height,
        pages=pages,
        words=words,
    )
    session.add(asset)
    session.flush()

    block = _build_block(asset)
    return StoredAsset(asset=asset, block=block)
