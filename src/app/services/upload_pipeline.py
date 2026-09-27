"""Spool in chunks, convert with a hard deadline, publish rows in a separate transaction."""
from __future__ import annotations
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

from fastapi import HTTPException
from app.core.config import settings
from app.services import files
from app.services.runtime import check_cancelled, run_tool
from app.services.storage import require_space, storage_error

logger = logging.getLogger(__name__)


def cleanup_asset(file_id):
    # Only a newly allocated UUID is accepted; never a name/path supplied by a client.
    if not re.fullmatch(r'[a-f0-9-]{36}', file_id):
        raise ValueError('Invalid generated asset id')
    for root in (files.ORIGINAL_DIR, files.PREVIEW_DIR, files.PAGES_DIR, files.DOC_HTML_DIR,
                 files.WAVEFORM_DIR, files.SLIDES_DIR, files.SLIDES_META_DIR,
                 files.EXCEL_SUMMARY_DIR, files.EXCEL_CHARTS_DIR, files.EXCEL_CHARTS_META_DIR,
                 files.VIDEO_DIR, files.CODE_DIR, files.MARKDOWN_DIR):
        for path in root.glob(file_id + '*'):
            if path.name != file_id and not path.name.startswith(file_id + '.'):
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                logger.error('upload_orphan_cleanup_failed asset=%s', file_id)


def prepare_upload(upload, note_id, user_id, upload_op_id=None):
    meta = files._classify_file(upload)
    limit = min(meta.max_bytes, settings.max_file_bytes)
    if meta.kind not in {'video', 'code', 'markdown'}:
        limit = min(limit, settings.max_conversion_bytes)
    file_id = files.generate_uuid()
    name = Path((upload.filename or 'upload').replace('\\', '/')).name
    if not name or len(name) > 255 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, 'Invalid filename')
    staging = files.UPLOAD_ROOT / '.staging'
    staging.mkdir(parents=True, exist_ok=True)
    require_space(staging)
    try:
        with tempfile.TemporaryDirectory(dir=staging, prefix='upload-') as job:
            job = Path(job)
            source = job / ('input' + meta.extension)
            size = 0
            upload.file.seek(0)
            with source.open('xb') as target:
                while True:
                    check_cancelled()
                    chunk = upload.file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, 'File exceeds the configured size limit')
                    require_space(staging, len(chunk))
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            if not size:
                raise HTTPException(400, 'Empty file')
            if meta.kind in {'docx', 'pptx', 'xlsx'}:
                try:
                    with zipfile.ZipFile(source) as archive:
                        if (len(archive.infolist()) > 10000 or
                            sum(item.file_size for item in archive.infolist()) > settings.max_archive_expanded_bytes):
                            raise HTTPException(413, 'Expanded document exceeds the conversion limit')
                except zipfile.BadZipFile:
                    raise HTTPException(422, 'Invalid document archive')
            spec = job / 'job.json'
            spec.write_text(json.dumps({'meta': meta.model_dump(), 'source': str(source),
                'file_id': file_id, 'original_name': name, 'note_id': note_id,
                'user_id': user_id, 'upload_op_id': upload_op_id}))
            env = dict(os.environ, OVC_UPLOAD_ROOT=str(files.UPLOAD_ROOT), OVC_CONVERSION_CHILD='1', OVC_CONVERSION_PARENT_PID=str(os.getpid()),
                       PYTHONPATH=str(Path(__file__).resolve().parents[2]), PYTHONDONTWRITEBYTECODE='1')
            env.update({name.upper(): str(getattr(settings, name)) for name in (
                'max_conversion_bytes', 'max_preview_bytes', 'storage_min_free_bytes',
                'ffmpeg_timeout_seconds', 'libreoffice_timeout_seconds', 'conversion_timeout_seconds')})
            run_tool([sys.executable, '-B', '-m', 'app.services.conversion_worker', str(spec)],
                     timeout=settings.conversion_timeout_seconds, env=env)
            result_path = job / 'result.json'
            if result_path.stat().st_size > settings.max_preview_bytes:
                raise HTTPException(413, 'Conversion result too large')
            result = json.loads(result_path.read_text())
            if 'error' in result:
                raise HTTPException(result['status'], result['error'])
            check_cancelled()
            asset = files.FileAsset(**result['asset'])
            if not Path(asset.path_original).is_file():
                raise HTTPException(500, 'Stored original is unavailable')
            return files.StoredAsset(asset=asset, block=result['block'])
    except BaseException as exc:
        cleanup_asset(file_id)
        logger.warning('upload_prepare_failed type=%s', type(exc).__name__)
        if isinstance(exc, OSError):
            raise storage_error(exc) from None
        raise
