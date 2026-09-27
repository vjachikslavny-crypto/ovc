"""Bounded disk writes; never removes existing user assets."""
import errno
import logging
import os
from pathlib import Path
import shutil
import tempfile

from fastapi import HTTPException
from app.core.config import settings


def require_space(root, incoming=0):
    if shutil.disk_usage(root).free < settings.storage_min_free_bytes + incoming:
        logging.getLogger(__name__).warning('storage_low_space')
        raise HTTPException(507, 'Insufficient storage space')


def storage_error(exc):
    if isinstance(exc, OSError) and exc.errno in (errno.ENOSPC, errno.EDQUOT):
        return HTTPException(507, 'Insufficient storage space')
    return HTTPException(500, 'Unable to store file')


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require_space(path.parent, len(data))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.partial-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise storage_error(exc) from None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
