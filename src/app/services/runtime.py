"""Bounded blocking jobs and child processes. No database sessions cross this boundary."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

from fastapi import HTTPException
from app.core.config import settings

logger = logging.getLogger(__name__)
cancel_event = ContextVar('runtime_cancel', default=None)
_lock = threading.Lock()
_jobs = set()
_processes = set()
_closing = False
_pool = ThreadPoolExecutor(max_workers=settings.runtime_workers, thread_name_prefix='ovc-job')
_slots = threading.BoundedSemaphore(settings.runtime_workers)


def check_cancelled():
    event = cancel_event.get()
    if _closing or (event and event.is_set()):
        raise HTTPException(503, 'Operation cancelled')


@contextmanager
def job_context():
    event = threading.Event()
    token = cancel_event.set(event)
    with _lock:
        if _closing:
            cancel_event.reset(token)
            raise HTTPException(503, 'Server is shutting down')
        _jobs.add(event)
    try:
        yield event
    finally:
        with _lock:
            _jobs.discard(event)
        cancel_event.reset(token)


async def run_blocking(function, *args, timeout=None, **kwargs):
    """Capacity stays occupied until a cancelled job really exits; no unbounded queue."""
    if _closing or not _slots.acquire(blocking=False):
        raise HTTPException(503, 'Processing capacity busy; retry later', headers={'Retry-After': '2'})
    context = copy_context()
    event = threading.Event()
    def work():
        token = cancel_event.set(event)
        with _lock:
            _jobs.add(event)
        try:
            check_cancelled()
            return function(*args, **kwargs)
        finally:
            with _lock:
                _jobs.discard(event)
            cancel_event.reset(token)
            _slots.release()
    try:
        future = _pool.submit(context.run, work)
    except BaseException:
        _slots.release()
        raise
    wrapped = asyncio.wrap_future(future)
    # Consume errors even when the client has disconnected.
    wrapped.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
    try:
        return await asyncio.wait_for(asyncio.shield(wrapped), timeout or settings.runtime_job_timeout_seconds)
    except asyncio.TimeoutError:
        event.set()
        logger.warning('runtime_job_timeout operation=%s', function.__name__)
        raise HTTPException(504, 'Processing timed out')
    except asyncio.CancelledError:
        event.set()
        raise


def _kill(process):
    try:
        if os.name == 'posix' and not os.getenv('OVC_CONVERSION_CHILD'):
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass


def run_tool(args, *, timeout=None, capture_output=False, text=False, check=True,
             stdout=None, stderr=None, env=None, cwd=None):
    """No shell, bounded diagnostic capture, hard deadline, reaped process group."""
    check_cancelled()
    executable = shutil.which(str(args[0]))
    if not executable:
        raise HTTPException(503, 'Required conversion tool is unavailable')
    command = [executable, *map(str, args[1:])]
    limit = settings.subprocess_output_bytes
    buffers = [bytearray(), bytearray()]
    def drain(pipe, buffer):
        try:
            for chunk in iter(lambda: pipe.read(4096), b''):
                buffer.extend(chunk)
                if len(buffer) > limit:
                    del buffer[:-limit]
        finally:
            pipe.close()
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=env, cwd=cwd,
        start_new_session=os.name == 'posix' and not os.getenv('OVC_CONVERSION_CHILD'))
    with _lock:
        _processes.add(process)
    readers = [threading.Thread(target=drain, args=(pipe, buffer), daemon=True)
               for pipe, buffer in zip((process.stdout, process.stderr), buffers)]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + (timeout or settings.conversion_timeout_seconds)
    try:
        while process.poll() is None:
            check_cancelled()
            if time.monotonic() >= deadline:
                logger.warning('subprocess_timeout tool=%s', Path(executable).name)
                raise HTTPException(504, 'Conversion timed out')
            time.sleep(.02)
    finally:
        # Also reap descendants left behind after their direct parent exits.
        _kill(process)
        process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=2)
        with _lock:
            _processes.discard(process)
    output = [bytes(b).decode('utf-8', errors='replace') if text else bytes(b) for b in buffers]
    if check and process.returncode:
        logger.warning('subprocess_failed tool=%s code=%s', Path(executable).name, process.returncode)
        raise HTTPException(422, 'File conversion failed')
    return subprocess.CompletedProcess(command, process.returncode, *output)


def start_runtime():
    global _closing
    _closing = False


def stop_runtime():
    global _closing
    _closing = True
    with _lock:
        events, processes = list(_jobs), list(_processes)
    for event in events:
        event.set()
    for process in processes:
        _kill(process)
    deadline = time.monotonic() + settings.shutdown_grace_seconds
    while time.monotonic() < deadline:
        with _lock:
            if not _jobs and not _processes:
                break
        time.sleep(.02)
    logging.getLogger('uvicorn.error').info('OVC runtime_shutdown pending_jobs=%s pending_processes=%s', len(_jobs), len(_processes))


async def run_for_request(request, function, *args, **kwargs):
    """Stop cancellable work when a fully parsed request loses its client."""
    task = asyncio.create_task(run_blocking(function, *args, **kwargs))
    try:
        while not task.done():
            if await request.is_disconnected():
                raise HTTPException(499, 'Client disconnected')
            await asyncio.wait({task}, timeout=.1)
        return await task
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
