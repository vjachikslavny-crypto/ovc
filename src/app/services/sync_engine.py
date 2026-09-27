"""Durable sync v1. HTTP is deliberately outside all local transactions.

Legacy protocol 0 rows, maps and cursors are retained but never consumed here.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import io
import json
import logging
from pathlib import Path
import random
import os
import tempfile
import threading
from urllib.parse import urlsplit, urlunsplit, quote
import uuid

import httpx
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, func, or_
from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.config import settings
from app.core.ownership import get_owned_note, get_owned_file
from app.db.models import (Note, NoteTag, NoteLink, FileAsset, SyncOutbox, SyncConflict,
    SyncEntityMap, SyncPeerState, SyncIdentity)
from app.db.session import get_session
from app.services.sync_protocol import (dumps, now, identity, lock_stream, note_payload,
    file_payload, file_ids, preserve_copy, advance_local_revision, record_relation_conflicts)

logger = logging.getLogger(__name__)
OP_CREATE_NOTE, OP_UPDATE_NOTE, OP_DELETE_NOTE = 'create_note', 'update_note', 'delete_note'
OP_COMMIT, OP_UPLOAD_FILE = 'commit', 'upload_file'
ACTIVE = ('pending', 'retry', 'inflight', 'auth_required')
TERMINAL = ('applied', 'conflict', 'failed_permanent')
_worker_lock, _sync_lock = threading.Lock(), threading.Lock()
_worker_stop = threading.Event()
_worker_started = False
_sync_thread = None


class RetryableSyncError(Exception):
    pass


class AuthRequired(Exception):
    pass


class PermanentSyncError(Exception):
    pass


def remote_key(url=None):
    parts = urlsplit(url or settings.sync_remote_base_url)
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Sync URL must be an HTTP(S) base URL without credentials/query/fragment')
    port = parts.port
    host = parts.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    netloc = host if not port or (parts.scheme, port) in [('https', 443), ('http', 80)] else f'{host}:{port}'
    normalized = urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip('/'), '', ''))
    return hashlib.sha256(normalized.encode()).hexdigest()


def _scope(session, uid):
    try:
        key = remote_key()
    except ValueError:
        raise HTTPException(503, 'Invalid remote sync base URL; check configuration')
    return (uid, identity(session, 'client_id'), key)


def _filter(model, scope):
    return (model.user_id == scope[0], model.client_id == scope[1], model.remote_key == scope[2])


def _mapping(session, scope, kind, local_id):
    return session.get(SyncEntityMap, (*scope, kind, local_id))


def _remote_mapping(session, scope, kind, remote_id):
    return session.execute(select(SyncEntityMap).where(*_filter(SyncEntityMap, scope),
        SyncEntityMap.entity_type == kind, SyncEntityMap.remote_id == remote_id)).scalar_one_or_none()


def _pending(session, scope, kind, entity_id, *, include_failed=False):
    return session.execute(select(SyncOutbox).where(*_filter(SyncOutbox, scope), SyncOutbox.protocol_version == 1,
        SyncOutbox.entity_type == kind, SyncOutbox.entity_id == entity_id,
        SyncOutbox.status.in_(ACTIVE + ('failed_permanent',) if include_failed else ACTIVE))
        .order_by(SyncOutbox.created_at, SyncOutbox.id)).scalars().all()


def _append(session, scope, kind, entity_id, op, payload, note_id=None, dependencies=None):
    session.flush()
    count = session.execute(select(func.count(SyncOutbox.id)).where(SyncOutbox.protocol_version == 1,
        SyncOutbox.status != 'applied')).scalar_one()
    if count >= settings.sync_outbox_max:
        raise HTTPException(503, 'Sync queue is full. Local draft is retained; resolve sync before retrying save.')
    previous = _pending(session, scope, kind, entity_id)
    mapping = _mapping(session, scope, kind, entity_id)
    deps = list(dependencies or [])
    if previous:
        deps.append({'op_id': previous[-1].id, 'base': True})
    item = SyncOutbox(id=str(uuid.uuid4()), protocol_version=1, user_id=scope[0], client_id=scope[1],
        remote_key=scope[2], entity_type=kind, entity_id=entity_id, note_id=note_id,
        entity_remote_id=mapping.remote_id if mapping else None,
        base_revision=mapping.remote_revision if mapping else None, op_type=op, payload_json=dumps(payload),
        dependency_json=dumps(deps), status='pending', tries=0)
    session.add(item)
    session.flush()
    return item


def _ensure_note(session, scope, note_id):
    mapping = _mapping(session, scope, 'note', note_id)
    if mapping:
        return None
    pending = _pending(session, scope, 'note', note_id)
    if pending:
        return pending[0].id
    note = get_owned_note(session, note_id, scope[0])
    # Establish identity first: attachment/link dependencies may be cyclic.
    skeleton = {'title': note.title, 'styleTheme': note.style_theme, 'blocks': [], 'tags': [], 'linksFrom': []}
    first = _append(session, scope, 'note', note_id, 'create', skeleton, note_id)
    return first.id


def _queue_file(session, scope, asset, *, preserve_parent=True):
    mapping = _mapping(session, scope, 'file', asset.id)
    pending = _pending(session, scope, 'file', asset.id)
    if mapping or pending:
        return pending[-1].id if pending else None
    deps = []
    parent_needs_snapshot = False
    if asset.note_id:
        first = _ensure_note(session, scope, asset.note_id)
        if first:
            deps.append({'op_id': first})
            parent_ops = _pending(session, scope, 'note', asset.note_id)
            parent_needs_snapshot = len(parent_ops) == 1 and parent_ops[0].op_type == 'create'
    payload = file_payload(asset)
    item = _append(session, scope, 'file', asset.id, 'upload', payload, asset.note_id, deps)
    if parent_needs_snapshot and preserve_parent:
        # An upload to an unmapped existing note must not leave its remote parent
        # as the empty identity shell and later pull that shell over local content.
        _queue_note(session, scope, get_owned_note(session, asset.note_id, scope[0]))
    return item.id


def _queue_note(session, scope, note, delete=False, visiting=None):
    visiting = set() if visiting is None else visiting
    if note.id in visiting:
        return
    visiting.add(note.id)
    deps = []
    if not delete:
        _ensure_note(session, scope, note.id)
    elif not _mapping(session, scope, 'note', note.id) and not _pending(session, scope, 'note', note.id):
        # Deleting an entirely local legacy note has no remote identity to delete.
        return
    snapshot = note_payload(session, note)
    if not delete:
        for fid in file_ids(snapshot['blocks']):
            dep = _queue_file(session, scope, get_owned_file(session, fid, scope[0]), preserve_parent=False)
            if dep:
                deps.append({'op_id': dep})
        for link in snapshot['linksFrom']:
            target = link['toId']
            dep = _ensure_note(session, scope, target)
            if dep:
                deps.append({'op_id': dep})
                target_ops = _pending(session, scope, 'note', target)
                if len(target_ops) == 1 and target_ops[0].op_type == 'create' and target != note.id:
                    _queue_note(session, scope, get_owned_note(session, target, scope[0]), visiting=visiting)
    _append(session, scope, 'note', note.id, 'delete' if delete else 'update', snapshot, note.id, deps)


def enqueue_sync_operation(session, op_type, payload, *, note_id=None, user_id=None):
    # Remote shell/shared-db never maintain an independent replica/outbox.
    if settings.sync_mode != 'remote-sync':
        return
    if not user_id or settings.auth_mode == 'none':
        raise HTTPException(409, 'Remote sync requires a real authenticated owner')
    if not settings.sync_remote_base_url:
        raise HTTPException(503, 'Remote sync URL is not configured')
    lock_stream(session)
    session.flush()
    scope = _scope(session, user_id)
    if op_type == OP_UPLOAD_FILE:
        asset = get_owned_file(session, payload['fileAssetId'], user_id)
        _queue_file(session, scope, asset)
        return
    ids = {note_id} if note_id else set()
    if op_type == OP_COMMIT:
        for action in payload.get('draft', []):
            ids.update(action[k] for k in ('noteId', 'fromId') if action.get(k))
    for nid in sorted(ids):
        note = session.get(Note, nid)
        if not note or note.user_id != user_id:
            raise HTTPException(404, 'Note not found')
        _queue_note(session, scope, note, delete=op_type == OP_DELETE_NOTE)


def _rewrite(value, file_map):
    if isinstance(value, str) and value.startswith('/files/'):
        parts = value.split('/')
        if len(parts) > 3:
            if parts[2] not in file_map:
                raise PermanentSyncError('Referenced file has no mapping')
            parts[2] = file_map[parts[2]]
            return '/'.join(parts)
    if isinstance(value, list):
        return [_rewrite(v, file_map) for v in value]
    if isinstance(value, dict):
        return {k: _rewrite(v, file_map) for k, v in value.items()}
    return value


def _remote_id(session, scope, kind, local_id):
    mapping = _mapping(session, scope, kind, local_id)
    if not mapping or mapping.status != 'mapped':
        raise PermanentSyncError('Missing scoped entity mapping')
    entity = session.get(Note if kind == 'note' else FileAsset, local_id)
    if not entity or entity.user_id != scope[0]:
        raise PermanentSyncError('Mapped entity ownership mismatch')
    return mapping.remote_id


def _queued_file(session, file_id, user_id):
    # A pending upload can precede an offline deletion of its parent. The server
    # will apply upload then tombstone in dependency order; ownership still holds.
    asset = session.get(FileAsset, file_id)
    parent = session.get(Note, asset.note_id) if asset and asset.note_id else None
    if not asset or asset.user_id != user_id or (asset.note_id and (not parent or parent.user_id != user_id)):
        raise PermanentSyncError('Local file ownership mismatch')
    return asset


def _claim(scope):
    with get_session(immediate=True) as session:
        lock_stream(session)
        peer = session.get(SyncPeerState, scope)
        if peer.auth_required:
            return None
        rows = session.execute(select(SyncOutbox).where(*_filter(SyncOutbox, scope),
            SyncOutbox.protocol_version == 1, SyncOutbox.status.in_(('pending', 'retry', 'inflight')),
            or_(SyncOutbox.next_retry_at.is_(None), SyncOutbox.next_retry_at <= now()))
            .order_by(SyncOutbox.created_at, SyncOutbox.id)).scalars().all()
        for item in rows:
            try:
                deps = json.loads(item.dependency_json)
                dependencies = [session.get(SyncOutbox, d['op_id']) for d in deps]
                if any(not d or (d.user_id, d.client_id, d.remote_key) != scope or d.status != 'applied' for d in dependencies):
                    item.last_error = 'Waiting for prerequisite acknowledgement'
                    continue
                if not item.wire_json:
                    payload = json.loads(item.payload_json)
                    if item.entity_type == 'note':
                        current = session.get(Note, item.entity_id)
                        if not current or current.user_id != scope[0]:
                            raise PermanentSyncError('Local note ownership mismatch')
                        files = {fid: _remote_id(session, scope, 'file', fid) for fid in file_ids(payload.get('blocks', []))}
                        payload['blocks'] = _rewrite(payload.get('blocks', []), files)
                        payload['linksFrom'] = [dict(l, toId=_remote_id(session, scope, 'note', l['toId'])) for l in payload.get('linksFrom', [])]
                        payload.pop('files', None)
                    else:
                        asset = _queued_file(session, item.entity_id, scope[0])
                        if payload.get('noteId'):
                            payload['noteId'] = _remote_id(session, scope, 'note', payload['noteId'])
                    remote_id, base = item.entity_remote_id, item.base_revision
                    if item.op_type != 'create' and item.entity_type == 'note':
                        remote_id = _remote_id(session, scope, 'note', item.entity_id)
                    for spec, dep in zip(deps, dependencies):
                        if spec.get('base'):
                            base = json.loads(dep.result_json)['revision']
                    wire = {'op_id': item.id, 'protocol_version': 1, 'user_id': peer.remote_user_id,
                        'client_id': scope[1], 'remote_key': peer.server_id, 'entity_type': item.entity_type,
                        'entity_local_id': item.entity_id, 'entity_remote_id': remote_id,
                        'operation_type': item.op_type, 'payload': payload, 'base_revision': base}
                    item.wire_json = dumps(wire)
                item.status, item.tries = 'inflight', item.tries + 1
                item.next_retry_at = now() + dt.timedelta(seconds=max(60, settings.sync_request_timeout_seconds * 3))
                item.last_error = None
                file_info = None
                if item.entity_type == 'file':
                    asset = _queued_file(session, item.entity_id, scope[0])
                    file_info = (asset.path_original, asset.filename, asset.mime)
                return {'id': item.id, 'wire': json.loads(item.wire_json), 'file': file_info}
            except (PermanentSyncError, HTTPException) as exc:
                item.status, item.last_error = 'failed_permanent', str(exc)
        return None


def _http(response):
    if response.status_code == 401:
        raise AuthRequired('Remote authentication required')
    if response.status_code >= 500 or response.status_code in (408, 425, 429):
        raise RetryableSyncError(f'Remote HTTP {response.status_code}')
    if response.status_code >= 400:
        raise PermanentSyncError(f'Remote HTTP {response.status_code}')
    return response


def _build_client(*, access_token=None):
    return httpx.Client(base_url=settings.sync_remote_base_url.rstrip('/') + '/',
        timeout=settings.sync_request_timeout_seconds, headers={'Authorization': f'Bearer {access_token}'}, follow_redirects=False)


def _verify_user(access_token, user_id):
    from app.core.security import get_current_user
    request = Request({'type': 'http', 'headers': [(b'authorization', f'Bearer {access_token}'.encode())]})
    user = get_current_user(request)
    context = getattr(request.state, 'auth_context', '')
    if user.id != user_id or context not in ('local-user', 'supabase-user'):
        raise AuthRequired('Verified user does not match queue owner')
    return context, user.supabase_id if context == 'supabase-user' else user.id


def _bind(scope, hello, principal):
    if hello.get('protocol_version') != 1:
        raise PermanentSyncError('Remote sync protocol is not supported')
    if (hello.get('auth_context'), hello.get('auth_subject')) != principal:
        raise AuthRequired('Remote authenticated identity differs from local identity')
    try:
        uuid.UUID(hello['server_id'])
    except (KeyError, ValueError, TypeError):
        raise PermanentSyncError('Remote server identity is invalid')
    with get_session(immediate=True) as session:
        lock_stream(session)
        peer = session.get(SyncPeerState, scope)
        if peer is None:
            peer = SyncPeerState(user_id=scope[0], client_id=scope[1], remote_key=scope[2])
            session.add(peer)
        if peer.server_id and (peer.server_id != hello['server_id'] or peer.remote_user_id != hello['user_id']):
            raise PermanentSyncError('Pinned server/account changed; explicit rebind required')
        peer.server_id, peer.remote_user_id = hello['server_id'], hello['user_id']
        peer.auth_required, peer.reachable, peer.last_error = False, True, None
        for row in session.execute(select(SyncOutbox).where(*_filter(SyncOutbox, scope),
            SyncOutbox.protocol_version == 1, SyncOutbox.status == 'auth_required')).scalars():
            row.status, row.next_retry_at = 'retry', None


def _error(scope, exc, item_id=None):
    auth = isinstance(exc, AuthRequired)
    permanent = isinstance(exc, PermanentSyncError)
    # Never persist response bodies, URLs containing tokens or transport exception text.
    message = str(exc) if auth or permanent else 'Remote temporarily unavailable; retry scheduled'
    with get_session(immediate=True) as session:
        lock_stream(session)
        peer = session.get(SyncPeerState, scope)
        if peer is None:
            peer = SyncPeerState(user_id=scope[0], client_id=scope[1], remote_key=scope[2])
            session.add(peer)
        peer.last_error, peer.auth_required, peer.reachable = message, auth, auth or permanent
        if item_id:
            row = session.get(SyncOutbox, item_id)
            if row and (row.user_id, row.client_id, row.remote_key) == scope and row.status != 'applied':
                row.status = 'auth_required' if auth else 'failed_permanent' if permanent else 'retry'
                row.last_error = message
                row.next_retry_at = now() + dt.timedelta(seconds=min(300, 2 ** min(row.tries - 1, 9)) * random.uniform(.8, 1.2))


def _preserve_pending(session, scope, note, remote_id, reason, op_id=None):
    rows = _pending(session, scope, 'note', note.id, include_failed=True)
    if not rows:
        return
    saved = preserve_copy(session, scope[0], note_payload(session, note))
    session.add(SyncConflict(user_id=scope[0], client_id=scope[1], remote_key=scope[2], op_id=op_id,
        local_note_id=note.id, remote_note_id=remote_id, kind=reason,
        payload_json=dumps({'original_id': note.id, 'conflict_copy_id': saved.id, 'client_id': scope[1],
            'source_op_id': op_id, 'local_revision': note.revision, 'snapshot': note_payload(session, note)})))
    for row in rows:
        row.status, row.last_error = 'conflict', 'Local version preserved in conflict copy and durable payload'


def _ack(scope, claim, result):
    if result.get('op_id') != claim['id']:
        raise RetryableSyncError('Acknowledgement operation mismatch')
    if result.get('status') not in ('applied', 'conflict'):
        if result.get('status') == 'auth_required':
            raise AuthRequired('Remote authentication required')
        if result.get('status') == 'retry':
            raise RetryableSyncError('Remote requested retry')
        if result.get('status') == 'failed_permanent':
            raise PermanentSyncError('Operation rejected by remote validation or ownership rules')
        raise RetryableSyncError('Incomplete acknowledgement')
    if not isinstance(result.get('revision'), int) or not isinstance(result.get('entity_remote_id'), str):
        raise RetryableSyncError('Incomplete acknowledgement')
    with get_session(immediate=True) as session:
        lock_stream(session)
        row = session.get(SyncOutbox, claim['id'])
        if not row or (row.user_id, row.client_id, row.remote_key) != scope:
            raise PermanentSyncError('Acknowledgement scope mismatch')
        if row.result_json:
            return
        mapping = _mapping(session, scope, row.entity_type, row.entity_id)
        if mapping is None:
            mapping = SyncEntityMap(user_id=scope[0], client_id=scope[1], remote_key=scope[2],
                entity_type=row.entity_type, local_id=row.entity_id, remote_id=result['entity_remote_id'])
            session.add(mapping)
        elif mapping.remote_id != result['entity_remote_id']:
            raise PermanentSyncError('Acknowledgement changes established mapping')
        mapping.remote_revision, mapping.status = result['revision'], 'mapped'
        if row.entity_type == 'file':
            mapping.sha256 = claim['wire']['payload']['sha256']
        if result['status'] == 'conflict' and row.entity_type == 'note':
            _preserve_pending(session, scope, session.get(Note, row.entity_id), mapping.remote_id, 'push_conflict', row.id)
        if row.entity_type == 'note':
            record_relation_conflicts(session, session.get(Note, row.entity_id),
                result.get('relation_conflicts', []), client_id=scope[1], remote_key=scope[2],
                op_id=row.id, remote_note_id=mapping.remote_id)
        row.status, row.result_json, row.last_error, row.next_retry_at = result['status'], dumps(result), None, None
        session.flush()
        # Ack changes only remote mapping/receipt. Pull reconciles content and
        # advances its local editor version independently of the remote number.


def _pull_local_id(session, scope, kind, rid):
    mapping = _remote_mapping(session, scope, kind, rid)
    if mapping:
        entity = session.get(Note if kind == 'note' else FileAsset, mapping.local_id)
        if entity is not None and entity.user_id != scope[0]:
            raise PermanentSyncError('Pull mapping ownership mismatch')
        if kind == 'note' and entity is None:
            session.add(Note(id=mapping.local_id, user_id=scope[0], title='Sync pending', tombstone=True))
            session.flush()
        return mapping.local_id
    lid = str(uuid.uuid4())
    session.add(SyncEntityMap(user_id=scope[0], client_id=scope[1], remote_key=scope[2],
        entity_type=kind, local_id=lid, remote_id=rid, status='placeholder'))
    if kind == 'note':
        # Hidden until its full snapshot arrives, including across page boundaries.
        session.add(Note(id=lid, user_id=scope[0], title='Sync pending', tombstone=True))
    session.flush()
    return lid


def _download_files(client, scope, page):
    manifests = {}
    for change in page:
        data = change['payload']
        for asset in ([data] if change['entity_type'] == 'file' else data.get('files', [])):
            manifests[asset['id']] = asset
    needed = []
    with get_session() as session:
        for rid, manifest in manifests.items():
            mapping = _remote_mapping(session, scope, 'file', rid)
            asset = session.get(FileAsset, mapping.local_id) if mapping else None
            if asset and asset.user_id != scope[0]:
                raise PermanentSyncError('Mapped file ownership mismatch')
            if asset and asset.hash_sha256 != manifest['sha256']:
                raise PermanentSyncError('Immutable remote file checksum changed')
            needed.append((rid, manifest, asset.path_original if asset else None))
    from app.services.files import UPLOAD_ROOT
    from app.services.storage import require_space
    downloads = []
    try:
        for rid, manifest, local_path in needed:
            if local_path and Path(local_path).is_file():
                with open(local_path, 'rb') as stream:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                if digest.hexdigest() == manifest['sha256']:
                    continue
            if not 0 <= manifest['size'] <= settings.max_file_bytes:
                raise PermanentSyncError('Remote file exceeds configured size limit')
            staging = UPLOAD_ROOT / '.staging'
            staging.mkdir(parents=True, exist_ok=True)
            require_space(staging, manifest['size'])
            with tempfile.NamedTemporaryFile(dir=staging, prefix='sync-', delete=False) as target:
                source = Path(target.name)
                downloads.append((manifest, source))
                digest, size = hashlib.sha256(), 0
                with client.stream('GET', f'api/sync/files/{quote(rid, safe="")}/original') as response:
                    _http(response)
                    for chunk in response.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > manifest['size'] or size > settings.max_file_bytes:
                            raise PermanentSyncError('Downloaded file exceeds manifest size')
                        require_space(staging, len(chunk))
                        target.write(chunk)
                        digest.update(chunk)
            if digest.hexdigest() != manifest['sha256'] or size != manifest['size']:
                raise PermanentSyncError('Downloaded file checksum mismatch')
        return downloads
    except BaseException:
        for _, source in downloads:
            source.unlink(missing_ok=True)
        raise


def _apply_page(scope, changes, downloads, cursor, next_cursor):
    from app.services.upload_pipeline import prepare_upload, cleanup_asset
    from app.services import files as file_service
    prepared, kept = [], []
    committed = False
    try:
        # Network, disk writes and converters finish BEFORE the cursor transaction.
        for manifest, source in downloads:
            with get_session() as session:
                mapping = _remote_mapping(session, scope, 'file', manifest['id'])
                existing = session.get(FileAsset, mapping.local_id) if mapping else None
            if existing:
                if existing.user_id != scope[0] or existing.hash_sha256 != manifest['sha256']:
                    raise PermanentSyncError('Mapped file identity mismatch')
                path = Path(existing.path_original).resolve()
                if not path.is_relative_to(file_service.UPLOAD_ROOT.resolve()):
                    raise PermanentSyncError('Mapped file path outside configured storage')
                path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, path)
                prepared.append((manifest, None, None))
            else:
                with source.open('rb') as stream:
                    upload = UploadFile(file=stream, filename=manifest['filename'], headers=Headers({'content-type': manifest['mime']}))
                    stored = prepare_upload(upload, None, scope[0])
                prepared.append((manifest, stored, stored.asset.id))
        committed = _apply_page_transaction(scope, changes, prepared, cursor, next_cursor, kept)
        return committed
    finally:
        for _, stored, original_id in prepared:
            if stored and (not committed or original_id not in kept):
                cleanup_asset(original_id)
        for _, source in downloads:
            source.unlink(missing_ok=True)


def _apply_page_transaction(scope, changes, prepared, cursor, next_cursor, kept):
    from app.services import files as file_service
    with get_session(immediate=True) as session:
        lock_stream(session)
        peer = session.get(SyncPeerState, scope)
        if peer.cursor != cursor:
            return False  # Another process already committed this page; reread cursor.
        for manifest, stored, original_id in prepared:
            mapping = _remote_mapping(session, scope, 'file', manifest['id'])
            existing = session.get(FileAsset, mapping.local_id) if mapping else None
            if existing:
                if existing.user_id != scope[0] or existing.hash_sha256 != manifest['sha256']:
                    raise PermanentSyncError('Mapped file identity mismatch')
                continue
            if stored is None:
                raise RetryableSyncError('File metadata changed during preparation')
            parent = _pull_local_id(session, scope, 'note', manifest['noteId']) if manifest.get('noteId') else None
            stored.asset.note_id = parent
            session.add(stored.asset)
            kept.append(original_id)
            if mapping:
                # Keep already published local URLs stable when recovering a lost row.
                stored.asset.id = mapping.local_id
                mapping.sha256, mapping.status = manifest['sha256'], 'mapped'
                session.flush()
            else:
                session.add(SyncEntityMap(user_id=scope[0], client_id=scope[1], remote_key=scope[2], entity_type='file',
                    local_id=stored.asset.id, remote_id=manifest['id'], remote_revision=1, sha256=manifest['sha256'], status='mapped'))
            session.flush()
        for change in changes:
            if change['entity_type'] == 'file':
                continue
            if change['entity_type'] != 'note':
                raise PermanentSyncError('Unsupported change type')
            rid, detail = change['entity_id'], change['payload']
            lid = _pull_local_id(session, scope, 'note', rid)
            note = session.get(Note, lid)
            if note.user_id != scope[0]:
                raise PermanentSyncError('Local note ownership mismatch')
            mapping = _mapping(session, scope, 'note', lid)
            if change['revision'] < mapping.remote_revision:
                continue
            pending = _pending(session, scope, 'note', lid, include_failed=True)
            if pending:
                if change['revision'] == mapping.remote_revision and not change['deleted']:
                    continue  # Own acknowledged older event must not replace a pending edit.
                if any(row.wire_json and not row.result_json and row.status in ('retry', 'inflight', 'auth_required') for row in pending):
                    # Replay the uncertain operation first. Advancing here could
                    # skip the newer remote edit after a lost acknowledgement.
                    raise RetryableSyncError('Waiting for uncertain operation receipt before pull')
                _preserve_pending(session, scope, note, rid, 'pull_conflict')
            ids = {fid: _remote_mapping(session, scope, 'file', fid) for fid in file_ids(detail.get('blocks', []))}
            if any(not v or v.status != 'mapped' for v in ids.values()):
                raise PermanentSyncError('Pull references an unavailable file')
            before, previous_stamp = note_payload(session, note), note.updated_at
            note.title = detail['title']
            note.style_theme = detail.get('styleTheme', 'clean')
            from app.agent.block_models import normalize_blocks
            note.blocks_json = dumps(normalize_blocks(_rewrite(detail.get('blocks', []), {k: v.local_id for k, v in ids.items()})))
            note.layout_hints, note.passport_json = dumps(detail.get('layoutHints', {})), dumps(detail.get('passport', {}))
            note.tombstone = bool(change['deleted'])
            note.created_at = dt.datetime.fromisoformat(detail['createdAt']).replace(tzinfo=None)
            session.query(NoteTag).filter(NoteTag.note_id == lid).delete(synchronize_session=False)
            for tag in sorted(set(detail.get('tags', []))):
                session.add(NoteTag(note_id=lid, tag=tag))
            session.query(NoteLink).filter(NoteLink.from_id == lid).delete(synchronize_session=False)
            for link in detail.get('linksFrom', []):
                target = _pull_local_id(session, scope, 'note', link['toId'])
                session.add(NoteLink(from_id=lid, to_id=target, reason=link.get('reason'), confidence=link.get('confidence')))
            session.flush()
            after = note_payload(session, note)
            # Own acknowledged snapshots need not invalidate an open editor when
            # the observable aggregate is unchanged. Neither clock is copied.
            note.updated_at = previous_stamp
            if any(before[key] != after[key] for key in (
                    'title', 'styleTheme', 'blocks', 'layoutHints', 'passport',
                    'createdAt', 'tombstone', 'tags', 'linksFrom')):
                advance_local_revision(note)
            mapping.remote_revision, mapping.status = change['revision'], 'mapped'
            from app.api.notes import _reindex_note
            _reindex_note(session, note)
            session.flush()
        peer.cursor, peer.last_success_at, peer.last_error = next_cursor, now(), None
    return True


def _check_worker_stop():
    if _worker_stop.is_set() and threading.current_thread() is _sync_thread:
        raise RetryableSyncError('Server shutting down')


def _pull(client, scope):
    pulled = 0
    while True:
        _check_worker_stop()
        with get_session() as session:
            peer = session.get(SyncPeerState, scope)
            cursor, server_id = peer.cursor, peer.server_id
        page = _http(client.get('api/sync/pull', params={'cursor': cursor, 'limit': min(100, settings.sync_batch_size)})).json()
        if page.get('server_id') != server_id or page.get('protocol_version') != 1:
            raise PermanentSyncError('Pull server identity/protocol changed')
        changes, next_cursor = page['changes'], page['next_cursor']
        sequences = [c['sequence'] for c in changes]
        if sequences != sorted(set(sequences)) or any(s <= cursor for s in sequences) or next_cursor != (sequences[-1] if sequences else cursor):
            raise PermanentSyncError('Invalid pull cursor ordering')
        downloads = _download_files(client, scope, changes)
        try:
            if _apply_page(scope, changes, downloads, cursor, next_cursor):
                pulled += len(changes)
                if not page.get('has_more'):
                    return pulled
        finally:
            for _, source in downloads:
                source.unlink(missing_ok=True)
        if not changes and page.get('has_more'):
            raise PermanentSyncError('Empty page cannot advance cursor')


def _cycle_result(user_id, pushed=0, pulled=0, reason=None):
    # Include durable failures discovered inside _claim, and those from earlier
    # cycles. `failed` has exactly the same meaning as in /sync/status.
    status = get_sync_status(user_id=user_id)
    result = {key: status[key] for key in ('failed', 'pending', 'retry', 'lastError', 'relationConflicts')}
    result.update(ok=not (reason or status['failed'] or status['retry'] or status['authRequired']),
                  pushed=pushed, pulled=pulled)
    if reason:
        result['reason'] = reason
    return result


def trigger_sync_now(*, access_token=None, user_id=None, background=False):
    if settings.sync_mode != 'remote-sync':
        return {'ok': False, 'reason': f'sync_mode_{settings.sync_mode}'}
    if not settings.sync_remote_base_url:
        return {'ok': False, 'reason': 'remote_base_url_empty'}
    if not user_id or not access_token or settings.auth_mode == 'none':
        return {'ok': False, 'reason': 'missing_verified_user_context'}
    with _sync_lock:
        with get_session() as session:
            scope = _scope(session, user_id)
        client = None
        pushed = pulled = 0
        claim = None
        try:
            principal = _verify_user(access_token, user_id)
            with get_session(immediate=True) as session:
                lock_stream(session)
                active = session.get(SyncIdentity, 'active_sync_user')
                if background and active and active.value != user_id:
                    return {'ok': False, 'reason': 'account_switched'}
                if active is None:
                    session.add(SyncIdentity(key='active_sync_user', value=user_id))
                elif not background:
                    active.value = user_id
            client = _build_client(access_token=access_token)
            hello = _http(client.get('api/sync/hello')).json()
            _bind(scope, hello, principal)
            for _ in range(settings.sync_batch_size):
                _check_worker_stop()
                claim = _claim(scope)
                if claim is None:
                    break
                try:
                    if claim['file']:
                        path, name, mime = claim['file']
                        with open(path, 'rb') as stream:
                            result = _http(client.post('api/sync/files', data={'operation': dumps(claim['wire'])},
                                files={'file': (name, stream, mime)})).json()
                    else:
                        result = _http(client.post('api/sync/push', json={'operations': [claim['wire']]})).json()['results'][0]
                    _ack(scope, claim, result)
                    pushed += 1
                except (AuthRequired, PermanentSyncError, RetryableSyncError, httpx.HTTPError, OSError) as exc:
                    _error(scope, exc, claim['id'])
                    if not isinstance(exc, PermanentSyncError):
                        return _cycle_result(user_id, pushed, pulled,
                            'auth_required' if isinstance(exc, AuthRequired) else 'retry')
                claim = None
            if settings.sync_pull_enabled:
                pulled = _pull(client, scope)
            with get_session() as session:
                peer = session.get(SyncPeerState, scope)
                peer.last_success_at, peer.reachable = now(), True
            return _cycle_result(user_id, pushed, pulled)
        except HTTPException as exc:
            if exc.status_code in (401, 403):
                error = AuthRequired('Local authentication required')
            elif exc.status_code >= 500 or exc.status_code == 429:
                error = RetryableSyncError(f'Local processing HTTP {exc.status_code}')
            else:
                error = PermanentSyncError(f'Local processing HTTP {exc.status_code}')
            _error(scope, error, claim['id'] if claim else None)
            return _cycle_result(user_id, pushed, pulled,
                'auth_required' if isinstance(error, AuthRequired) else 'sync_error')
        except (AuthRequired, PermanentSyncError, RetryableSyncError, httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as exc:
            _error(scope, exc, claim['id'] if claim else None)
            return _cycle_result(user_id, pushed, pulled,
                'auth_required' if isinstance(exc, AuthRequired) else 'sync_error')
        finally:
            if client is not None:
                client.close()


def get_sync_status(*, user_id=None):
    with get_session() as session:
        cid = identity(session, 'client_id')
        configuration_error = None
        try:
            key = remote_key() if settings.sync_remote_base_url else ''
        except ValueError:
            key, configuration_error = '', 'Invalid remote sync base URL; check configuration'
        scope = (user_id, cid, key)
        peer = session.get(SyncPeerState, scope) if user_id else None
        counts = dict(session.execute(select(SyncOutbox.status, func.count()).where(
            *_filter(SyncOutbox, scope), SyncOutbox.protocol_version == 1).group_by(SyncOutbox.status)).all())
        failed_row = session.execute(select(SyncOutbox).where(*_filter(SyncOutbox, scope),
            SyncOutbox.protocol_version == 1, SyncOutbox.status == 'failed_permanent')
            .order_by(SyncOutbox.created_at, SyncOutbox.id).limit(1)).scalar_one_or_none()
        relation_conflicts = session.execute(select(func.count()).select_from(SyncConflict).where(
            *_filter(SyncConflict, scope), SyncConflict.kind == 'relation_target_deleted')).scalar_one()
        legacy = session.execute(select(func.count()).select_from(SyncOutbox).where(
            or_(SyncOutbox.protocol_version == 0, SyncOutbox.protocol_version.is_(None)), SyncOutbox.user_id == user_id)).scalar_one() if user_id else 0
        return {'protocolVersion': 1, 'userId': user_id, 'clientId': cid, 'remoteKey': key,
            'serverId': peer.server_id if peer else None, 'cursor': peer.cursor if peer else 0,
            'enabled': settings.sync_mode == 'remote-sync', 'mode': settings.sync_mode,
            'workerEnabled': settings.sync_worker_enabled, 'desktopMode': settings.desktop_mode,
            'remoteConfigured': bool(settings.sync_remote_base_url),
            'pending': sum(counts.get(s, 0) for s in ACTIVE), 'retry': counts.get('retry', 0),
            'done': counts.get('applied', 0), 'conflicts': counts.get('conflict', 0),
            'relationConflicts': relation_conflicts,
            'failed': counts.get('failed_permanent', 0), 'quarantinedLegacy': legacy,
            'remoteReachable': peer.reachable if peer else None, 'authRequired': peer.auth_required if peer else False,
            'lastError': configuration_error or (peer.last_error if peer else None)
                or (failed_row.last_error if failed_row else None),
            'lastSuccessAt': peer.last_success_at.isoformat() if peer and peer.last_success_at else None}


def start_sync_worker_once():
    global _worker_started, _sync_thread
    if settings.sync_mode != 'remote-sync' or not settings.sync_worker_enabled or settings.auth_mode == 'none':
        return
    from app.core.security import get_current_user
    try:
        token = settings.sync_bearer_token
        request = Request({'type': 'http', 'headers': [(b'authorization', f'Bearer {token}'.encode())]})
        uid = get_current_user(request).id
        _verify_user(token, uid)
    except (HTTPException, AuthRequired):
        settings.sync_worker_enabled = False
        logger.error('Sync worker disabled: configured token has no verified owner')
        return
    with _worker_lock:
        if _worker_started:
            return
        _worker_stop.clear()
        def loop():
            while not _worker_stop.is_set():
                try:
                    result = trigger_sync_now(access_token=token, user_id=uid, background=True)
                    if result.get('reason') in ('auth_required', 'account_switched'):
                        settings.sync_worker_enabled = False
                        logger.warning('Background sync paused: authentication expired or active account changed')
                        return
                except Exception:
                    logger.exception('Sync worker cycle failed')
                _worker_stop.wait(max(3, settings.sync_poll_seconds))
        _sync_thread = threading.Thread(target=loop, name='ovc-sync-worker', daemon=True)
        _sync_thread.start()
        _worker_started = True
        logger.info('Sync v1 worker bound to a verified owner; legacy queue quarantined')


def stop_sync_worker():
    global _worker_started
    _worker_stop.set()
    if _sync_thread and _sync_thread.is_alive():
        _sync_thread.join(timeout=settings.shutdown_grace_seconds)
    if not _sync_thread or not _sync_thread.is_alive():
        _worker_started = False
