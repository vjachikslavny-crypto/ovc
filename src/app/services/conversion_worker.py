"""Internal process entrypoint: trusted job file only, never an HTTP endpoint."""
import json
import os
import signal
import threading
import time


def _watch_parent():
    expected = int(os.environ.get('OVC_CONVERSION_PARENT_PID', '0'))
    if not expected or os.name != 'posix':
        return
    def watch():
        while True:
            if os.getppid() != expected:
                # Parent crashed: this isolated group contains this worker and its tools.
                os.killpg(os.getpgrp(), signal.SIGKILL)
            time.sleep(.2)
    threading.Thread(target=watch, name='parent-watch', daemon=True).start()


_watch_parent()
from pathlib import Path
import sys
from fastapi import HTTPException
# Register ORM metadata for transient DTOs; no engine/session is created here.
from app.models.user import User
from app.models.session import RefreshToken
from app.services.files import FileMetadata, _prepare_file
from app.services.storage import storage_error
from app.core.config import settings


def main():
    spec_path = Path(sys.argv[1])
    spec = json.loads(spec_path.read_text())
    if 'operation' in spec:
        return viewer(spec_path, spec)
    spec['meta'] = FileMetadata(**spec['meta'])
    spec['source'] = Path(spec['source'])
    try:
        stored = _prepare_file(**spec)
        for column in stored.asset.__table__.columns:
            value = getattr(stored.asset, column.name)
            if column.name.startswith('path_') and value and value != stored.asset.path_original:
                path = Path(value)
                if path.is_file() and path.stat().st_size > settings.max_preview_bytes:
                    raise HTTPException(413, 'Preview exceeds configured size limit')
        result = {'asset': {c.name: getattr(stored.asset, c.name) for c in stored.asset.__table__.columns
                            if getattr(stored.asset, c.name) is not None}, 'block': stored.block}
    except HTTPException as exc:
        result = {'status': exc.status_code, 'error': 'File processing failed' if exc.status_code >= 500 else str(exc.detail)}
    except OSError as exc:
        error = storage_error(exc)
        result = {'status': error.status_code, 'error': error.detail}
    except Exception:
        result = {'status': 422, 'error': 'Invalid or unsupported file contents'}
    (spec_path.parent / 'result.json').write_text(json.dumps(result))


def viewer(spec_path, spec):
    from types import SimpleNamespace
    from app.services import files
    import csv
    asset = SimpleNamespace(**spec['asset'])
    output = spec_path.parent / 'output'
    try:
        if Path(asset.path_original).stat().st_size > settings.max_conversion_bytes:
            raise HTTPException(413, 'Conversion input too large')
        if spec['operation'] == 'pdf':
            data = files._render_pdf_page(Path(asset.path_original).read_bytes(), spec['page'], spec['scale'])
            if not data:
                raise HTTPException(422, 'Unable to render PDF page')
            output.write_bytes(data)
        elif spec['operation'] == 'excel-window':
            output.write_text(json.dumps(files._read_excel_window(asset, spec['sheet'], spec['offset'], spec['limit'])))
        elif spec['operation'] == 'excel-csv':
            workbook = None
            try:
                if asset.kind == 'xlsx':
                    workbook = files.load_workbook(asset.path_original, read_only=True, data_only=True)
                    rows = workbook[spec['sheet']].iter_rows(values_only=True)
                elif asset.kind == 'xls':
                    workbook = files.xlrd.open_workbook(asset.path_original, on_demand=True)
                    sheet = workbook.sheet_by_name(spec['sheet'])
                    rows = (sheet.row_values(i) for i in range(sheet.nrows))
                else:
                    raise HTTPException(415, 'Unsupported spreadsheet')
                with output.open('w', newline='') as stream:
                    writer = csv.writer(stream)
                    for row in rows:
                        writer.writerow([files._clean_cell(v) for v in row])
                        if stream.tell() > settings.max_preview_bytes:
                            raise HTTPException(413, 'Export exceeds configured preview limit')
            finally:
                if workbook:
                    if hasattr(workbook, 'close'):
                        workbook.close()
                    elif hasattr(workbook, 'release_resources'):
                        workbook.release_resources()
        else:
            raise HTTPException(422, 'Unknown conversion operation')
        if output.stat().st_size > settings.max_preview_bytes:
            raise HTTPException(413, 'Preview too large')
        result = {'ok': True}
    except HTTPException as exc:
        result = {'status': exc.status_code, 'error': str(exc.detail)}
    except Exception:
        result = {'status': 422, 'error': 'Unable to process document'}
    (spec_path.parent / 'result.json').write_text(json.dumps(result))


if __name__ == '__main__':
    main()
