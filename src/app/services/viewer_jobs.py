"""On-demand viewers share the same bounded process path as upload conversion."""
import json
import os
from pathlib import Path
import sys
import tempfile
from fastapi import HTTPException
from app.core.config import settings
from app.services import files
from app.services.runtime import run_tool


def render_viewer(asset, operation, **options):
    with tempfile.TemporaryDirectory(prefix='ovc-viewer-', dir=files.UPLOAD_ROOT) as job:
        job = Path(job)
        spec = {'asset': {k: getattr(asset, k) for k in ('path_original', 'path_excel_summary', 'kind')},
                'operation': operation, **options}
        path = job / 'job.json'
        path.write_text(json.dumps(spec))
        env = dict(os.environ, OVC_UPLOAD_ROOT=str(files.UPLOAD_ROOT), OVC_CONVERSION_CHILD='1', OVC_CONVERSION_PARENT_PID=str(os.getpid()),
                   PYTHONPATH=str(Path(__file__).resolve().parents[2]), PYTHONDONTWRITEBYTECODE='1')
        env.update({name.upper(): str(getattr(settings, name)) for name in (
            'max_conversion_bytes', 'max_preview_bytes', 'storage_min_free_bytes',
            'ffmpeg_timeout_seconds', 'libreoffice_timeout_seconds', 'conversion_timeout_seconds')})
        run_tool([sys.executable, '-B', '-m', 'app.services.conversion_worker', str(path)],
                 env=env, timeout=settings.conversion_timeout_seconds)
        result = json.loads((job / 'result.json').read_text())
        if 'error' in result:
            raise HTTPException(result['status'], result['error'])
        if (job / 'output').stat().st_size > settings.max_preview_bytes:
            raise HTTPException(413, 'Preview too large')
        return (job / 'output').read_bytes()
