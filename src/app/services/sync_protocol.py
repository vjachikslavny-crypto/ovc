"""Canonical v1 server journal and note aggregate/revision contract.

No HTTP is performed here. Mutation, change event and idempotency receipt share
one transaction. Legacy rows (version 0) are never treated as protocol receipts.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Optional, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, text, or_

from app.agent.block_models import normalize_blocks
from app.api.note_models import NoteCreateRequest
from app.core.ownership import get_owned_note, get_owned_file
from app.db.models import (Note, NoteTag, NoteLink, FileAsset, SyncIdentity,
                           SyncAppliedOp, SyncChangeLog, SyncConflict)

SYNC_PROTOCOL_VERSION = 1


def now():
    return dt.datetime.utcnow()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def identity(session, key):
    value = '0' if key == 'sequence' else str(uuid.uuid4())
    session.execute(text('INSERT INTO sync_identity (key,value) VALUES (:k,:v) ON CONFLICT (key) DO NOTHING'), {'k': key, 'v': value})
    return session.execute(select(SyncIdentity.value).where(SyncIdentity.key == key)).scalar_one()


def lock_stream(session):
    identity(session, 'sequence')
    # Serializes sequence allocation in commit order (also across server workers).
    session.execute(text("UPDATE sync_identity SET value=value WHERE key='sequence'"))


def check_revision(note, expected, *, required=False):
    if expected is None:
        if required:
            raise HTTPException(409, 'base_revision required')
        return
    value = str(expected).strip('"')
    if value not in {str(note.revision), f'r{note.revision}', note.updated_at.isoformat()}:
        raise HTTPException(409, 'Note changed on server; local draft must be reconciled')


def file_payload(asset):
    return {'id': asset.id, 'noteId': asset.note_id, 'filename': asset.filename,
            'mime': asset.mime, 'kind': asset.kind, 'size': asset.size, 'sha256': asset.hash_sha256,
            'originalUrl': f'/files/{asset.id}/original'}


def note_payload(session, note):
    uid = note.user_id
    links = []
    for link in session.execute(select(NoteLink).where(NoteLink.from_id == note.id)).scalars():
        target = session.get(Note, link.to_id)
        if target and target.user_id == uid and not target.tombstone:
            links.append({'toId': target.id, 'reason': link.reason, 'confidence': link.confidence})
    return {'id': note.id, 'title': note.title, 'styleTheme': note.style_theme,
            'blocks': json.loads(note.blocks_json), 'layoutHints': json.loads(note.layout_hints),
            'passport': json.loads(note.passport_json), 'revision': note.revision,
            'updatedAt': note.updated_at.isoformat(), 'createdAt': note.created_at.isoformat(),
            'tombstone': bool(note.tombstone),
            'tags': sorted(session.execute(select(NoteTag.tag).where(NoteTag.note_id == note.id)).scalars()),
            'linksFrom': links,
            'files': [file_payload(f) for f in session.execute(select(FileAsset).where(
                FileAsset.user_id == uid, or_(FileAsset.note_id == note.id,
                    FileAsset.id.in_(file_ids(json.loads(note.blocks_json)))))).scalars()]}


def record_change(session, uid, entity_type, entity_id, operation, revision, payload, deleted=False):
    lock_stream(session)
    session.execute(text("UPDATE sync_identity SET value=CAST(CAST(value AS BIGINT)+1 AS TEXT) WHERE key='sequence'"))
    sequence = int(session.execute(select(SyncIdentity.value).where(SyncIdentity.key == 'sequence')).scalar_one())
    session.add(SyncChangeLog(protocol_version=1, sequence=sequence, user_id=uid,
        entity_type=entity_type, entity_id=entity_id, op_type=operation, server_version=revision,
        deleted=deleted, payload_json=dumps(payload)))
    session.flush()
    return sequence


def advance_local_revision(note):
    """Local CRUD/editor/AI version; remote revisions belong only to sync maps."""
    note.revision = int(note.revision or 0) + 1
    stamp = now()
    # Legacy If-Match also accepts updatedAt. Never reuse it, even after clock skew.
    note.updated_at = max(stamp, note.updated_at + dt.timedelta(microseconds=1)) if note.updated_at else stamp


def record_note_change(session, note, operation='update', *, bump=True):
    if bump:
        advance_local_revision(note)
    session.add(note)
    session.flush()
    snapshot = note_payload(session, note)
    record_change(session, note.user_id, 'note', note.id, operation, note.revision, snapshot, bool(note.tombstone))
    return snapshot


def record_file_change(session, asset):
    session.flush()
    record_change(session, asset.user_id, 'file', asset.id, 'upload', 1, file_payload(asset))


def file_ids(value):
    if isinstance(value, str) and value.startswith('/files/'):
        parts = value.split('/')
        return {parts[2]} if len(parts) > 3 else set()
    if isinstance(value, dict):
        return set().union(*(file_ids(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(file_ids(v) for v in value))
    return set()


class Relation(BaseModel):
    toId: str
    reason: Optional[str] = None
    confidence: Optional[float] = None


def replace_note(session, note, payload, uid, *, allow_deleted_links=False):
    data = NoteCreateRequest.model_validate(payload)
    blocks = normalize_blocks(payload.get('blocks', []))
    for fid in file_ids(blocks):
        get_owned_file(session, fid, uid)
    links = payload.get('linksFrom', [])
    tags = payload.get('tags', [])
    if not isinstance(links, list) or not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise HTTPException(422, 'Invalid relation snapshot')
    links = [Relation.model_validate(link).model_dump() for link in links]
    live_links, relation_conflicts = [], []
    for link in links:
        target = session.get(Note, link['toId'])
        if allow_deleted_links and target and target.user_id == uid and target.tombstone:
            relation_conflicts.append({'kind': 'relation_target_deleted', 'relation': link})
        else:
            get_owned_note(session, link['toId'], uid)
            live_links.append(link)
    note.title, note.style_theme = data.title, data.style_theme
    note.blocks_json, note.layout_hints, note.passport_json = dumps(blocks), dumps(data.layout_hints), dumps(data.passport)
    session.add(note)
    session.flush()

    # Shared canonical block/text indexing; publish only after the transaction commits.
    from app.api.notes import _reindex_note
    _reindex_note(session, note)

    session.query(NoteTag).filter(NoteTag.note_id == note.id).delete(synchronize_session=False)
    for tag in sorted(set(tags)):
        session.add(NoteTag(note_id=note.id, tag=tag))
    session.query(NoteLink).filter(NoteLink.from_id == note.id).delete(synchronize_session=False)
    seen = set()
    for link in live_links:
        key = (link['toId'], link.get('reason'))
        if key not in seen:
            session.add(NoteLink(from_id=note.id, to_id=key[0], reason=key[1], confidence=link.get('confidence')))
            seen.add(key)
    session.flush()
    return relation_conflicts


def record_relation_conflicts(session, note, issues, **scope):
    for issue in issues:
        session.add(SyncConflict(user_id=note.user_id, local_note_id=note.id,
            kind='relation_target_deleted', payload_json=dumps(issue), **scope))


def preserve_copy(session, uid, payload, *, title_suffix=' (conflict copy)'):
    """Editor recovery and sync copies own metadata; immutable bytes may be shared."""
    copy = Note(id=str(uuid.uuid4()), user_id=uid, title='')
    incoming = json.loads(dumps(payload))
    incoming['title'] = incoming.get('title', 'Note') + title_suffix
    session.add(copy)
    session.flush()
    mappings = {}
    for fid in file_ids(incoming.get('blocks', [])):
        asset = session.get(FileAsset, fid)
        parent = session.get(Note, asset.note_id) if asset and asset.note_id else None
        if not asset or asset.user_id != uid or (asset.note_id and (not parent or parent.user_id != uid)):
            raise HTTPException(404, 'File not found')
        clone = FileAsset(**{col.name: getattr(asset, col.name) for col in FileAsset.__table__.columns
                             if col.name not in {'id', 'note_id', 'upload_op_id'}})
        clone.id, clone.note_id = str(uuid.uuid4()), copy.id
        session.add(clone)
        record_file_change(session, clone)
        mappings[fid] = clone.id
    def rewrite(value):
        if isinstance(value, str) and value.startswith('/files/'):
            parts = value.split('/')
            if len(parts) > 3 and parts[2] in mappings:
                parts[2] = mappings[parts[2]]
                return '/'.join(parts)
        if isinstance(value, dict):
            return {k: rewrite(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v) for v in value]
        return value
    incoming['blocks'] = rewrite(incoming.get('blocks', []))
    issues = replace_note(session, copy, incoming, uid, allow_deleted_links=True)
    record_relation_conflicts(session, copy, issues)
    record_note_change(session, copy, 'conflict_copy')
    return copy


class SyncOperation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    op_id: uuid.UUID
    protocol_version: Literal[1]
    user_id: str
    client_id: uuid.UUID
    remote_key: str
    entity_type: Literal['note', 'file']
    entity_local_id: str
    entity_remote_id: Optional[str] = None
    operation_type: Literal['create', 'update', 'delete', 'upload']
    payload: dict = Field(default_factory=dict)
    base_revision: Optional[int] = Field(default=None, ge=0)


def operation_dict(op):
    return op.model_dump(mode='json')


def receipt(session, uid, op):
    lock_stream(session)
    if op.user_id != uid or op.remote_key != identity(session, 'server_id'):
        raise HTTPException(403, 'Sync identity mismatch')
    fingerprint = hashlib.sha256(dumps(operation_dict(op)).encode()).hexdigest()
    old = session.get(SyncAppliedOp, str(op.op_id))
    if old:
        if (old.protocol_version != 1 or old.user_id != uid or old.client_id != str(op.client_id)
                or old.request_hash != fingerprint or not old.result_json):
            raise HTTPException(409, 'Operation identity reused with different scope or payload')
        return json.loads(old.result_json), fingerprint
    return None, fingerprint


def store_receipt(session, uid, op, fingerprint, result):
    session.add(SyncAppliedOp(op_id=str(op.op_id), protocol_version=1, user_id=uid,
        client_id=str(op.client_id), entity_type=op.entity_type, entity_id=result.get('entity_remote_id'),
        request_hash=fingerprint, result_json=dumps(result)))
    session.flush()


def apply_note_operation(session, uid, op):
    previous, fingerprint = receipt(session, uid, op)
    if previous is not None:
        return previous
    if op.entity_type != 'note' or op.operation_type == 'upload':
        raise HTTPException(422, 'Use multipart sync/files for file upload')
    conflict = False
    relation_conflicts = []
    if op.operation_type == 'create':
        if op.entity_remote_id is not None or op.base_revision is not None:
            raise HTTPException(422, 'Create cannot target an existing entity')
        note = Note(id=str(uuid.uuid4()), user_id=uid, title=op.payload.get('title', ''))
        relation_conflicts = replace_note(session, note, op.payload, uid, allow_deleted_links=True)
        snapshot = record_note_change(session, note, 'create')
    else:
        note = session.execute(select(Note).where(Note.id == op.entity_remote_id).with_for_update()).scalar_one_or_none()
        if not note or note.user_id != uid:
            raise HTTPException(404, 'Note not found')
        if op.base_revision is None:
            raise HTTPException(422, 'base_revision required')
        conflict = bool(note.tombstone or op.base_revision != note.revision)
        if conflict:
            copy = None
            if op.payload.get('title'):
                copy = preserve_copy(session, uid, op.payload)
            metadata = {'source_op_id': str(op.op_id), 'original_id': note.id,
                'base_revision': op.base_revision, 'current_revision': note.revision,
                'client_id': str(op.client_id), 'incoming': op.payload,
                'conflict_copy_id': copy.id if copy else None}
            session.add(SyncConflict(user_id=uid, client_id=str(op.client_id), remote_key=op.remote_key,
                op_id=str(op.op_id), local_note_id=note.id, remote_note_id=note.id,
                kind='revision_conflict', payload_json=dumps(metadata)))
            snapshot = note_payload(session, note)
        elif op.operation_type == 'update':
            relation_conflicts = replace_note(session, note, op.payload, uid, allow_deleted_links=True)
            snapshot = record_note_change(session, note)
        else:
            note.tombstone = True
            snapshot = record_note_change(session, note, 'delete')
    result = {'op_id': str(op.op_id), 'status': 'conflict' if conflict else 'applied',
              'entity_remote_id': note.id, 'revision': note.revision, 'snapshot': snapshot}
    if conflict:
        result['conflict'] = {k: v for k, v in metadata.items() if k != 'incoming'}
    if relation_conflicts:
        record_relation_conflicts(session, note, relation_conflicts, client_id=str(op.client_id),
            remote_key=op.remote_key, op_id=str(op.op_id), remote_note_id=note.id)
        result['relation_conflicts'] = relation_conflicts
    store_receipt(session, uid, op, fingerprint, result)
    return result


def bootstrap_log(session, uid):
    # Existing notes have no v1 events. Snapshot once; never replay old outbox rows.
    lock_stream(session)
    for note in session.execute(select(Note).where(Note.user_id == uid)).scalars():
        found = session.execute(select(SyncChangeLog.id).where(SyncChangeLog.protocol_version == 1,
            SyncChangeLog.user_id == uid, SyncChangeLog.entity_type == 'note', SyncChangeLog.entity_id == note.id)).first()
        if not found:
            record_note_change(session, note, 'bootstrap', bump=False)
    for asset in session.execute(select(FileAsset).where(FileAsset.user_id == uid)).scalars():
        if asset.note_id:
            parent = session.get(Note, asset.note_id)
            if not parent or parent.user_id != uid or parent.tombstone:
                continue
        found = session.execute(select(SyncChangeLog.id).where(SyncChangeLog.protocol_version == 1,
            SyncChangeLog.user_id == uid, SyncChangeLog.entity_type == 'file', SyncChangeLog.entity_id == asset.id)).first()
        if not found:
            record_file_change(session, asset)
