"""Stage 3–4 server contract; all databases and uploaded bytes are disposable.

Run with pytest so conftest.py installs the isolated environment before app imports.
These tests deliberately use real local bearer authentication, separate committed
sessions, and the public sync routes, without starting a background sync worker.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from threading import Barrier
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

if os.environ.get("OVC_ISOLATED_TESTS") != "1":
    raise RuntimeError("Run with pytest; tests/conftest.py must isolate DB/storage first")

from app.api import sync as sync_api
from app.core.config import settings
from app.core.security import create_access_token
from app.db import session as db
from app.db.models import (
    FileAsset, Note, NoteLink, NoteTag, SyncAppliedOp, SyncChangeLog,
    SyncConflict, SyncIdentity, SyncOutbox,
)
from app.db.sync_schema import upgrade
from app.main import app
from app.models.user import User
from app.services import files as file_service
from app.services import sync_protocol as protocol


class ProtocolServer:
    def __init__(self, upload_root):
        self.upload_root = upload_root
        self.client_id = str(uuid.uuid4())
        self.headers = {
            uid: {"Authorization": f"Bearer {create_access_token(uid)}"}
            for uid in ("alice", "bob")
        }
        self.client = TestClient(app, headers=self.headers["alice"])
        with db.get_session() as session:
            self.server_id = protocol.identity(session, "server_id")

    def operation(self, *, title="Offline note", payload=None, **overrides):
        raw = {
            "op_id": str(uuid.uuid4()), "protocol_version": 1,
            "user_id": "alice", "client_id": self.client_id,
            "remote_key": self.server_id, "entity_type": "note",
            "entity_local_id": str(uuid.uuid4()), "entity_remote_id": None,
            "operation_type": "create", "base_revision": None,
            "payload": payload if payload is not None else {
                "title": title, "styleTheme": "clean", "blocks": [],
                "layoutHints": {}, "passport": {}, "tags": [], "linksFrom": [],
            },
        }
        raw.update(overrides)
        return raw

    def apply(self, raw, uid="alice"):
        with db.get_session(immediate=True) as session:
            return protocol.apply_note_operation(
                session, uid, protocol.SyncOperation.model_validate(raw)
            )

    def push(self, *operations, client=None):
        response = (client or self.client).post(
            "/api/sync/push", json={"operations": list(operations)}
        )
        assert response.status_code == 200, response.text
        results = response.json()["results"]
        assert len(results) == len(operations)
        assert [r["op_id"] for r in results] == [op["op_id"] for op in operations]
        return results

    def pull(self, cursor=0, limit=100, client=None):
        response = (client or self.client).get(
            "/api/sync/pull", params={"cursor": cursor, "limit": limit}
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["server_id"] == self.server_id
        return page

    def upload_operation(self, data=b"# offline attachment\n", **overrides):
        return self.operation(entity_type="file", operation_type="upload", payload={
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "filename": "attachment.md", "mime": "text/markdown",
            **overrides,
        })

    def upload(self, op, data=b"# offline attachment\n", *, client=None,
               filename=None, mime=None):
        return (client or self.client).post(
            "/api/sync/files", data={"operation": protocol.dumps(op)},
            files={"file": (
                filename if filename is not None else op["payload"]["filename"], data,
                mime if mime is not None else op["payload"]["mime"],
            )},
        )


@pytest.fixture
def server(isolated_database, monkeypatch, tmp_path):
    # The autouse fixture guards the engine before dropping any tables.
    assert db.engine.url.get_backend_name() in {"sqlite", "postgresql"}
    assert settings.auth_mode == "local"
    assert not app.dependency_overrides
    monkeypatch.setattr(settings, "sync_mode", "off")
    monkeypatch.setattr(settings, "desktop_mode", False)
    root = tmp_path / "uploads"
    original_root = file_service.UPLOAD_ROOT
    for name, value in list(vars(file_service).items()):
        if isinstance(value, Path) and (name == "UPLOAD_ROOT" or name.endswith("_DIR")):
            relative = value.relative_to(original_root)
            directory = root / relative
            directory.mkdir(parents=True, exist_ok=True)
            monkeypatch.setattr(file_service, name, directory)
    with db.get_session() as session:
        for uid in ("alice", "bob"):
            session.add(User(id=uid, username=f"sync-{uid}", password_hash="unused",
                             is_active=True, role="user"))
    harness = ProtocolServer(root)
    yield harness
    harness.client.close()


def counts():
    with db.get_session() as session:
        return {
            model.__tablename__: session.query(model).count()
            for model in (Note, NoteTag, NoteLink, FileAsset, SyncAppliedOp,
                          SyncChangeLog, SyncConflict, SyncOutbox)
        }


def assert_no_mutations():
    assert all(value == 0 for value in counts().values())


def test_hello_has_stable_server_identity_and_authenticated_user(server):
    first = server.client.get("/api/sync/hello")
    assert first.status_code == 200
    hello = first.json()
    assert hello == {
        "protocol_version": 1, "server_id": server.server_id, "user_id": "alice",
        "auth_context": "local-user", "auth_subject": "alice",
    }
    assert str(uuid.UUID(hello["server_id"])) == hello["server_id"]
    other = TestClient(app, headers=server.headers["bob"])
    try:
        response = other.get("/api/sync/hello")
        assert response.status_code == 200
        assert response.json() == {**hello, "user_id": "bob", "auth_subject": "bob"}
        assert server.client.get("/api/sync/hello").json() == hello
        assert_no_mutations()
    finally:
        other.close()


@pytest.mark.parametrize("method,path", [
    ("get", "/api/sync/hello"), ("post", "/api/sync/push"),
    ("get", "/api/sync/pull"), ("post", "/api/sync/files"),
])
@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
def test_sync_routes_require_local_auth(server, method, path, authorization):
    client = TestClient(app)
    try:
        response = client.request(method, path, headers=(
            {"Authorization": authorization} if authorization else {}
        ))
        assert response.status_code == 401, response.text
        assert_no_mutations()
    finally:
        client.close()


def test_auth_none_is_not_a_sync_credential(server, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "none")
    assert server.client.get("/api/sync/hello").status_code == 403
    assert_no_mutations()


def test_create_and_retry_replay_exact_durable_receipt(server):
    op = server.operation(title="Сохранённая заметка")
    first = server.push(op)[0]
    assert first["status"] == "applied"
    assert first["revision"] == 1
    assert first["entity_remote_id"] != op["entity_local_id"]
    assert first["snapshot"]["title"] == op["payload"]["title"]
    before = counts()
    assert server.push(op, op) == [first, first]
    assert counts() == before
    with db.get_session() as session:
        row = session.get(SyncAppliedOp, op["op_id"])
        assert row.protocol_version == 1 and row.user_id == "alice"
        assert row.client_id == op["client_id"]
        assert row.request_hash == hashlib.sha256(protocol.dumps(op).encode()).hexdigest()
        assert json.loads(row.result_json) == first
        event = session.query(SyncChangeLog).one()
        assert event.entity_id == first["entity_remote_id"]
        assert json.loads(event.payload_json) == first["snapshot"]
        assert event.server_version == 1 and event.protocol_version == 1


def test_receipt_fingerprint_ignores_json_object_key_order(server):
    op = server.operation()
    first = server.apply(op)
    reordered = dict(reversed(list(op.items())))
    reordered["payload"] = dict(reversed(list(op["payload"].items())))
    assert server.apply(reordered) == first
    assert counts()["notes"] == counts()["sync_applied_ops"] == 1


@pytest.mark.parametrize("field,value", [
    ("payload", {"title": "Changed bytes"}),
    ("client_id", "22222222-2222-4222-8222-222222222222"),
    ("entity_local_id", "different-local-note"),
    ("remote_key", "another-server"), ("user_id", "bob"),
])
def test_reused_op_id_cannot_change_payload_or_scope(server, field, value):
    op = server.operation()
    first = server.apply(op)
    before = counts()
    changed = deepcopy(op)
    changed[field] = value
    result = server.push(changed)[0]
    assert result["status"] == "failed_permanent"
    assert "snapshot" not in result and "entity_remote_id" not in result
    assert counts() == before
    assert server.apply(op) == first


def test_other_user_cannot_replay_someone_elses_receipt(server):
    op = server.operation()
    server.apply(op)
    op["user_id"] = "bob"
    client = TestClient(app, headers=server.headers["bob"])
    try:
        result = server.push(op, client=client)[0]
        assert result["status"] == "failed_permanent"
        assert "snapshot" not in result and "entity_remote_id" not in result
        assert server.pull(client=client)["changes"] == []
    finally:
        client.close()


def test_legacy_applied_marker_never_acknowledges_v1_operation(server):
    op = server.operation()
    with db.get_session() as session:
        session.add(SyncAppliedOp(op_id=op["op_id"], user_id="alice", entity_type="note",
                                 entity_id="historical-note"))
    result = server.push(op)[0]
    assert result["status"] == "failed_permanent"
    with db.get_session() as session:
        row = session.get(SyncAppliedOp, op["op_id"])
        assert row.protocol_version == 0 and row.result_json is None
        assert session.query(Note).count() == session.query(SyncChangeLog).count() == 0


def test_update_replaces_tags_and_links_and_replays_old_snapshot(server):
    target = server.apply(server.operation(title="Link target"))
    op = server.operation()
    op["payload"]["tags"] = ["z", "a", "a"]
    op["payload"]["linksFrom"] = [
        {"toId": target["entity_remote_id"], "reason": "related", "confidence": 0.7}
    ] * 2
    created = server.apply(op)
    assert created["snapshot"]["tags"] == ["a", "z"]
    assert len(created["snapshot"]["linksFrom"]) == 1
    update = server.operation(operation_type="update", title="Replaced",
                              entity_remote_id=created["entity_remote_id"], base_revision=1)
    updated = server.push(update)[0]
    assert updated["status"] == "applied" and updated["revision"] == 2
    assert updated["snapshot"]["tags"] == updated["snapshot"]["linksFrom"] == []
    before = counts()
    assert server.push(op, update) == [created, updated]
    assert counts() == before
    with db.get_session() as session:
        note = session.get(Note, created["entity_remote_id"])
        assert note.title == "Replaced" and note.revision == 2
        assert session.query(NoteTag).count() == session.query(NoteLink).count() == 0


def test_concurrent_note_edits_preserve_winner_and_one_conflict_copy(server):
    created = server.apply(server.operation())
    barrier = Barrier(2)
    operations = [server.operation(
        operation_type="update", entity_remote_id=created["entity_remote_id"],
        base_revision=1, title=title, client_id=str(uuid.uuid4()),
    ) for title in ("Laptop edit", "Desktop edit")]

    def send(op):
        client = TestClient(app, headers=server.headers["alice"])
        try:
            barrier.wait(timeout=10)
            return server.push(op, client=client)[0]
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, operations))
    assert sorted(r["status"] for r in results) == ["applied", "conflict"]
    winner = next(r for r in results if r["status"] == "applied")
    loser = next(r for r in results if r["status"] == "conflict")
    losing_op = next(op for op in operations if op["op_id"] == loser["op_id"])
    assert winner["revision"] == loser["revision"] == 2
    with db.get_session() as session:
        original = session.get(Note, created["entity_remote_id"])
        copy = session.get(Note, loser["conflict"]["conflict_copy_id"])
        assert original.title == winner["snapshot"]["title"]
        assert copy.user_id == "alice" and copy.revision == 1
        assert copy.title == losing_op["payload"]["title"] + " (conflict copy)"
        conflict = session.query(SyncConflict).one()
        assert conflict.op_id == losing_op["op_id"]
        assert json.loads(conflict.payload_json)["incoming"] == losing_op["payload"]
    before = counts()
    assert server.push(losing_op)[0] == loser
    assert counts() == before


def test_concurrent_duplicate_create_has_one_mutation_receipt_and_event(server):
    op = server.operation()
    barrier = Barrier(2)

    def send(_):
        client = TestClient(app, headers=server.headers["alice"])
        try:
            barrier.wait(timeout=10)
            return server.push(op, client=client)[0]
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(send, range(2)))
    assert first == second and first["status"] == "applied"
    with db.get_session() as session:
        assert session.query(Note).count() == session.query(SyncAppliedOp).count() == 1
        assert session.query(SyncChangeLog).count() == 1


@pytest.mark.parametrize("operation_type", ["update", "delete"])
def test_existing_note_requires_base_revision(server, operation_type):
    created = server.apply(server.operation())
    before = counts()
    op = server.operation(operation_type=operation_type,
                          entity_remote_id=created["entity_remote_id"])
    assert server.push(op)[0]["status"] == "failed_permanent"
    assert counts() == before
    with db.get_session() as session:
        note = session.get(Note, created["entity_remote_id"])
        assert note.revision == 1 and not note.tombstone


def test_delete_is_durable_tombstone_and_stale_edit_cannot_resurrect(server):
    created = server.apply(server.operation())
    remote_id = created["entity_remote_id"]
    delete = server.operation(operation_type="delete", entity_remote_id=remote_id,
                              base_revision=1, payload={})
    deleted = server.push(delete)[0]
    assert deleted["status"] == "applied" and deleted["revision"] == 2
    assert deleted["snapshot"]["tombstone"] is True
    stale = server.operation(operation_type="update", entity_remote_id=remote_id,
                             base_revision=1, title="Must survive as conflict")
    conflict = server.push(stale)[0]
    assert conflict["status"] == "conflict"
    assert conflict["snapshot"]["tombstone"] is True
    assert server.push(delete)[0] == deleted
    with db.get_session() as session:
        note = session.get(Note, remote_id)
        assert note.tombstone and note.revision == 2 and note.title == "Offline note"
        copy = session.get(Note, conflict["conflict"]["conflict_copy_id"])
        assert copy is not None and not copy.tombstone
    events = server.pull()["changes"]
    deletion = [e for e in events if e["entity_id"] == remote_id and e["deleted"]]
    assert len(deletion) == 1 and deletion[0]["revision"] == 2
    assert deletion[0]["payload"] == deleted["snapshot"]


@pytest.mark.parametrize("operation_type", ["update", "delete"])
@pytest.mark.parametrize("owner", ["bob", None])
def test_push_cannot_mutate_foreign_or_unowned_note(server, operation_type, owner):
    with db.get_session() as session:
        session.add(Note(id="private-note", user_id=owner, title="Private", revision=7))
    before = counts()
    op = server.operation(operation_type=operation_type, entity_remote_id="private-note",
                          base_revision=7, title="Stolen")
    result = server.push(op)[0]
    assert result["status"] == "failed_permanent"
    assert "snapshot" not in result
    assert counts() == before
    assert server.pull()["changes"] == []
    with db.get_session() as session:
        note = session.get(Note, "private-note")
        assert note.user_id == owner and note.title == "Private" and note.revision == 7
        assert not note.tombstone


@pytest.mark.parametrize("relation", ["link", "file"])
@pytest.mark.parametrize("owner", ["bob", None])
def test_note_aggregate_cannot_reference_foreign_or_unowned_data(server, relation, owner):
    with db.get_session() as session:
        session.add(Note(id="private-target", user_id=owner, title="Private"))
        session.add(FileAsset(id="private-file", user_id=owner, note_id="private-target",
                              kind="markdown", filename="secret.md", mime="text/markdown",
                              size=6, path_original=str(server.upload_root / "absent")))
    op = server.operation()
    if relation == "link":
        op["payload"]["linksFrom"] = [{"toId": "private-target", "reason": "stolen"}]
    else:
        op["payload"]["blocks"] = [{"id": "private-block", "type": "image", "data": {
            "src": "/files/private-file/original", "alt": "private",
        }}]
    before = counts()
    result = server.push(op)[0]
    assert result["status"] == "failed_permanent"
    assert counts() == before


def test_partial_batch_keeps_valid_operations_before_and_after_invalid_one(server):
    first = server.operation(title="Before")
    bad = server.operation(title="Bad relation")
    bad["payload"]["linksFrom"] = [{"toId": "missing-note"}]
    last = server.operation(title="After")
    results = server.push(first, bad, last)
    assert [r["status"] for r in results] == ["applied", "failed_permanent", "applied"]
    with db.get_session() as session:
        assert {n.title for n in session.query(Note)} == {"Before", "After"}
        assert {r.op_id for r in session.query(SyncAppliedOp)} == {first["op_id"], last["op_id"]}
        assert session.query(SyncChangeLog).count() == 2
    assert server.push(first, bad, last) == results


@pytest.mark.parametrize("mutation", [
    {"protocol_version": 0}, {"op_id": "not-a-uuid"}, {"client_id": "invalid"},
    {"unexpected": "field"}, {"base_revision": -1},
    {"entity_type": "file", "operation_type": "upload"},
])
def test_invalid_operation_does_not_poison_batch(server, mutation):
    bad = server.operation(**mutation)
    good = server.operation()
    results = server.push(bad, good)
    assert [r["status"] for r in results] == ["failed_permanent", "applied"]
    assert counts()["notes"] == counts()["sync_applied_ops"] == 1


@pytest.mark.parametrize("size", [0, 101])
def test_push_batch_size_is_bounded(server, size):
    response = server.client.post("/api/sync/push", json={
        "operations": [server.operation() for _ in range(size)]
    })
    assert response.status_code == 422
    assert_no_mutations()


@pytest.mark.parametrize("stage", ["record_change", "store_receipt"])
def test_receipt_and_change_failure_rolls_back_note_and_sequence(server, monkeypatch, stage):
    op = server.operation()
    original = getattr(protocol, stage)

    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected crash before commit")

    with monkeypatch.context() as patched:
        patched.setattr(protocol, stage, fail_after_flush)
        with pytest.raises(RuntimeError, match="injected crash"):
            server.apply(op)
    assert_no_mutations()
    with db.get_session() as session:
        counter = session.get(SyncIdentity, "sequence")
        assert counter is None or counter.value == "0"
    result = server.apply(op)
    assert result["status"] == "applied" and result["revision"] == 1
    with db.get_session() as session:
        assert session.query(SyncChangeLog).one().sequence == 1


def test_failed_update_restores_prior_aggregate_and_receipt(server, monkeypatch):
    target = server.apply(server.operation(title="Target"))
    op = server.operation()
    op["payload"]["tags"] = ["keep"]
    op["payload"]["linksFrom"] = [{"toId": target["entity_remote_id"], "reason": "keep"}]
    first = server.apply(op)
    update = server.operation(title="Rolled back", operation_type="update",
                              entity_remote_id=first["entity_remote_id"], base_revision=1)
    before = counts()
    original = protocol.store_receipt

    def fail_after_receipt(*args):
        original(*args)
        raise RuntimeError("injected receipt failure")

    with monkeypatch.context() as patched:
        patched.setattr(protocol, "store_receipt", fail_after_receipt)
        with pytest.raises(RuntimeError, match="injected receipt failure"):
            server.apply(update)
    assert counts() == before
    with db.get_session() as session:
        assert protocol.note_payload(session, session.get(Note, first["entity_remote_id"])) == first["snapshot"]
        assert session.get(SyncAppliedOp, update["op_id"]) is None
    assert server.apply(update)["revision"] == 2


@pytest.mark.parametrize("error,status", [
    (OperationalError("UPDATE notes", {}, Exception("database is locked")), "retry"),
    (HTTPException(503, "temporarily unavailable"), "retry"),
    (HTTPException(401, "authentication expired"), "auth_required"),
])
def test_batch_classifies_retry_and_auth_failure_without_losing_peers(server, monkeypatch, error, status):
    first, failed, last = [server.operation(title=title) for title in ("Before", "Retry", "After")]
    original = sync_api.apply_note_operation

    def fail_one(session, uid, op):
        result = original(session, uid, op)
        if str(op.op_id) == failed["op_id"]:
            raise error
        return result

    client = TestClient(app, headers=server.headers["alice"], raise_server_exceptions=False)
    try:
        with monkeypatch.context() as patched:
            patched.setattr(sync_api, "apply_note_operation", fail_one)
            results = server.push(first, failed, last, client=client)
        assert [r["status"] for r in results] == ["applied", status, "applied"]
        with db.get_session() as session:
            assert session.get(SyncAppliedOp, failed["op_id"]) is None
            assert {n.title for n in session.query(Note)} == {"Before", "After"}
            assert session.query(SyncChangeLog).count() == 2
        assert server.push(failed)[0]["status"] == "applied"
    finally:
        client.close()


def test_sequence_pagination_handles_timestamp_ties_and_user_gaps(server):
    alice_results = []
    for index in range(5):
        alice_results.append(server.apply(server.operation(title=f"Alice {index}")))
        server.apply(server.operation(title=f"Bob {index}", user_id="bob"), uid="bob")
    with db.get_session() as session:
        session.query(SyncChangeLog).update({"created_at": dt.datetime(2026, 1, 1)})
        expected = [row.sequence for row in session.query(SyncChangeLog).filter_by(
            user_id="alice").order_by(SyncChangeLog.sequence)]
    cursor, events = 0, []
    for has_more, expected_size in ((True, 2), (True, 2), (False, 1)):
        page = server.pull(cursor=cursor, limit=2)
        assert page["has_more"] is has_more
        assert len(page["changes"]) == expected_size
        assert all(change["sequence"] > cursor for change in page["changes"])
        cursor = page["next_cursor"]
        assert cursor == page["changes"][-1]["sequence"]
        events.extend(page["changes"])
    assert [event["sequence"] for event in events] == expected
    assert len(set(expected)) == 5
    assert [event["entity_id"] for event in events] == [r["entity_remote_id"] for r in alice_results]
    for event, result in zip(events, alice_results):
        assert event["entity_type"] == "note" and event["revision"] == 1
        assert event["deleted"] is False and event["payload"] == result["snapshot"]
    empty = server.pull(cursor=cursor, limit=2)
    assert empty["changes"] == [] and empty["next_cursor"] == cursor
    assert empty["has_more"] is False


def test_pull_bootstraps_existing_notes_once_without_rewriting_legacy_queue(server):
    with db.get_session() as session:
        session.add_all([
            Note(id="existing", user_id="alice", title="Existing", revision=8),
            Note(id="deleted", user_id="alice", title="Deleted", revision=3, tombstone=True),
            Note(id="foreign", user_id="bob", title="Private"),
            Note(id="orphan", title="Unknown owner"),
            SyncOutbox(id="legacy", user_id="alice", op_type="create_note", payload_json=' {"old": true} ', status="pending", tries=4),
            SyncChangeLog(id="legacy-event", user_id="alice", entity_type="note", entity_id="existing",
                          op_type="update", server_version=2, payload_json='{"old": true}'),
        ])
    first = server.pull()
    assert {change["entity_id"] for change in first["changes"]} == {"existing", "deleted"}
    assert {change["entity_id"]: change["revision"] for change in first["changes"]} == {"existing": 8, "deleted": 3}
    before = counts()
    assert server.pull() == first
    assert counts() == before
    with db.get_session() as session:
        row = session.get(SyncOutbox, "legacy")
        assert row.protocol_version == 0 and row.status == "pending" and row.tries == 4
        assert row.payload_json == ' {"old": true} ' and row.wire_json is None
        assert session.get(SyncChangeLog, "legacy-event").sequence is None


@pytest.mark.parametrize("query", ["cursor=-1", "limit=0", "limit=501", "cursor=not-an-int"])
def test_pull_rejects_invalid_cursor_or_limit(server, query):
    assert server.client.get(f"/api/sync/pull?{query}").status_code == 422
    assert_no_mutations()


@pytest.mark.parametrize("attached", [False, True])
def test_upload_retry_returns_same_mapping_and_durable_checksum(server, attached):
    parent = server.apply(server.operation()) if attached else None
    note_id = parent["entity_remote_id"] if parent else None
    op = server.upload_operation(**({"noteId": note_id} if attached else {}))
    first = server.upload(op)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["status"] == "applied" and result["revision"] == 1
    assert result["entity_remote_id"] != op["entity_local_id"]
    assert result["snapshot"]["sha256"] == op["payload"]["sha256"]
    before = counts()
    paths = {path for path in server.upload_root.rglob("*") if path.is_file()}
    second = server.upload(op)
    assert second.status_code == 200 and second.json() == result
    assert counts() == before
    assert {path for path in server.upload_root.rglob("*") if path.is_file()} == paths
    with db.get_session() as session:
        asset = session.get(FileAsset, result["entity_remote_id"])
        assert asset.user_id == "alice" and asset.note_id == note_id
        assert asset.hash_sha256 == op["payload"]["sha256"]
        assert asset.upload_op_id == op["op_id"]
        stored = Path(asset.path_original)
        assert stored.is_relative_to(server.upload_root)
        assert stored.read_bytes() == b"# offline attachment\n"
        assert json.loads(session.get(SyncAppliedOp, op["op_id"]).result_json) == result
    changes = server.pull()["changes"]
    uploads = [change for change in changes if change["entity_type"] == "file"]
    assert len(uploads) == 1 and uploads[0]["payload"] == result["snapshot"]


@pytest.mark.parametrize("mismatch", ["sha256", "size", "filename", "mime", "bytes"])
def test_upload_metadata_mismatch_has_no_receipt_row_or_file(server, mismatch):
    op = server.upload_operation()
    data = b"# offline attachment\n"
    if mismatch == "bytes":
        data = b"# different bytes\n"
    else:
        op["payload"][mismatch] = {
            "sha256": "0" * 64, "size": len(data) + 1,
            "filename": "wrong.md", "mime": "text/plain",
        }[mismatch]
    response = server.upload(op, data, filename="attachment.md", mime="text/markdown")
    assert response.status_code == 422, response.text
    assert_no_mutations()
    assert not any(path.is_file() for path in server.upload_root.rglob("*"))


def test_upload_retry_checks_bytes_even_when_receipt_exists(server):
    op = server.upload_operation()
    first = server.upload(op)
    assert first.status_code == 200
    before = counts()
    response = server.upload(op, b"# corrupted retry\n")
    assert response.status_code == 422
    assert counts() == before
    assert server.upload(op).json() == first.json()


def test_upload_op_id_cannot_be_reused_for_new_bytes(server):
    op = server.upload_operation()
    first = server.upload(op)
    assert first.status_code == 200
    before = counts()
    changed = server.upload_operation(b"new bytes")
    changed["op_id"] = op["op_id"]
    response = server.upload(changed, b"new bytes")
    assert response.status_code == 409, response.text
    assert counts() == before


@pytest.mark.parametrize("owner", ["bob", None])
def test_upload_cannot_attach_to_foreign_or_unowned_note(server, owner):
    with db.get_session() as session:
        session.add(Note(id="private-note", user_id=owner, title="Private"))
    before = counts()
    response = server.upload(server.upload_operation(noteId="private-note"))
    assert response.status_code == 404, response.text
    assert counts() == before
    assert not any(path.is_file() for path in server.upload_root.rglob("*"))


def test_upload_receipt_failure_rolls_back_asset_event_and_ack(server, monkeypatch):
    op = server.upload_operation()
    original = sync_api.store_receipt

    def fail_after_receipt(*args):
        original(*args)
        raise RuntimeError("injected upload receipt failure")

    client = TestClient(app, headers=server.headers["alice"], raise_server_exceptions=False)
    try:
        with monkeypatch.context() as patched:
            patched.setattr(sync_api, "store_receipt", fail_after_receipt)
            response = server.upload(op, client=client)
        assert response.status_code == 500
        assert_no_mutations()
        retry = server.upload(op)
        assert retry.status_code == 200 and retry.json()["status"] == "applied"
        assert counts()["files"] == counts()["sync_applied_ops"] == counts()["sync_change_log"] == 1
    finally:
        client.close()


def test_migration_preserves_legacy_rows_payloads_and_scope_tables(tmp_path):
    """Exercise ALTER TABLE against an actual old schema, not create_all()."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    schemas = {
        "sync_outbox": "id TEXT PRIMARY KEY, op_type TEXT NOT NULL, user_id TEXT, note_id TEXT, payload_json TEXT NOT NULL, status TEXT NOT NULL, tries INTEGER NOT NULL, last_error TEXT, created_at DATETIME, updated_at DATETIME",
        "sync_applied_ops": "op_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT, created_at DATETIME",
        "sync_change_log": "id TEXT PRIMARY KEY, user_id TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, op_type TEXT NOT NULL, server_version INTEGER NOT NULL, deleted BOOLEAN NOT NULL, payload_json TEXT NOT NULL, created_at DATETIME",
        "sync_conflicts": "id TEXT PRIMARY KEY, local_note_id TEXT, remote_note_id TEXT, kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_at DATETIME",
        "sync_state": "user_id TEXT PRIMARY KEY, cursor TEXT, last_error TEXT",
        "sync_note_map": "local_note_id TEXT PRIMARY KEY, remote_note_id TEXT NOT NULL UNIQUE, created_at DATETIME, updated_at DATETIME",
    }
    rows = {
        "sync_outbox": {"id": "queued", "op_type": "create_note", "user_id": None, "note_id": "old-note", "payload_json": ' {"title":"Старое", "path":"/untouched"} ', "status": "pending", "tries": 9, "last_error": "offline"},
        "sync_applied_ops": {"op_id": "old-op", "user_id": "alice", "entity_type": "note", "entity_id": "old-note"},
        "sync_change_log": {"id": "old-event", "user_id": "alice", "entity_type": "note", "entity_id": "old-note", "op_type": "update", "server_version": 4, "deleted": 0, "payload_json": '{ "old": true }'},
        "sync_conflicts": {"id": "old-conflict", "local_note_id": "old-note", "remote_note_id": "remote", "kind": "note_conflict", "payload_json": '{ "draft": "keep" }'},
        "sync_state": {"user_id": "alice", "cursor": "2025-01-01T00:00:00", "last_error": "keep"},
        "sync_note_map": {"local_note_id": "old-note", "remote_note_id": "old-remote"},
    }
    try:
        with engine.begin() as connection:
            for table, columns in schemas.items():
                connection.exec_driver_sql(f"CREATE TABLE {table} ({columns})")
                row = rows[table]
                connection.execute(text(
                    f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join(':' + key for key in row)})"
                ), row)
            before = {table: dict(connection.execute(text(f"SELECT * FROM {table}")).mappings().one())
                      for table in schemas}
            upgrade(connection)
            identities = dict(connection.execute(text("SELECT key,value FROM sync_identity")).all())
            upgrade(connection)
            assert dict(connection.execute(text("SELECT key,value FROM sync_identity")).all()) == identities
            assert identities["sequence"] == "0" and identities["schema_version"] == "1"
            assert uuid.UUID(identities["server_id"]) and uuid.UUID(identities["client_id"])
            for table, old in before.items():
                current = connection.execute(text(f"SELECT * FROM {table}")).mappings().one()
                assert {key: current[key] for key in old} == old
            for table in ("sync_outbox", "sync_applied_ops", "sync_change_log"):
                assert connection.execute(text(f"SELECT protocol_version FROM {table}")).scalar_one() == 0
            assert connection.execute(text("SELECT sequence FROM sync_change_log")).scalar_one() is None
            assert connection.execute(text("SELECT wire_json FROM sync_outbox")).scalar_one() is None
            assert connection.execute(text("SELECT result_json FROM sync_applied_ops")).scalar_one() is None
            assert connection.execute(text("SELECT dependency_json FROM sync_outbox")).scalar_one() == "[]"
            assert {"sync_peer_state", "sync_entity_map"} <= set(inspect(connection).get_table_names())
            for table in ("sync_peer_state", "sync_entity_map"):
                assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
        # Uniqueness must also be installed on upgraded (not just newly created) tables.
        with engine.begin() as connection:
            connection.execute(text("UPDATE sync_change_log SET sequence=1 WHERE id='old-event'"))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("INSERT INTO sync_change_log (id,user_id,entity_type,entity_id,op_type,server_version,deleted,payload_json,sequence) VALUES ('duplicate','alice','note','x','create',1,0,'{}',1)"))
    finally:
        engine.dispose()


def test_web_editor_ai_and_sync_share_one_revision_and_tombstone_contract(server):
    response = server.client.post('/api/notes', json={'title': 'Shared version'})
    assert response.status_code == 201
    note = response.json()
    nid, revision = note['id'], note['revision']
    assert response.headers['etag'] == f'"r{revision}"'
    applied = server.client.post('/api/commit', json={'draft': [{'type': 'add_tag', 'noteId': nid, 'tag': 'tag'}],
        'baseRevisions': {nid: revision}})
    assert applied.status_code == 200 and applied.json()['revisions'][nid] == revision + 1
    assert server.client.patch(f'/api/notes/{nid}', json={'title': 'Stale'}, headers={'If-Match': f'"r{revision}"'}).status_code == 409
    assert server.client.post('/api/commit', json={'draft': [{'type': 'add_tag', 'noteId': nid, 'tag': 'stale'}],
        'baseRevisions': {nid: revision}}).status_code == 409
    conflict = server.push(server.operation(operation_type='update', entity_remote_id=nid,
        base_revision=revision, title='Offline version'))[0]
    assert conflict['status'] == 'conflict' and conflict['revision'] == revision + 1
    current = server.client.get(f'/api/notes/{nid}').json()
    # Previous clients may still submit timestamp If-Match.
    response = server.client.patch(f'/api/notes/{nid}', json={'title': 'Timestamp compatible'}, headers={'If-Match': '"' + current['updatedAt'] + '"'})
    assert response.status_code == 200 and response.json()['revision'] == revision + 2
    assert server.client.delete(f'/api/notes/{nid}', headers={'If-Match': f'"r{revision + 2}"'}).status_code == 200
    assert server.client.get(f'/api/notes/{nid}').status_code == 404
    assert nid not in {n['id'] for n in server.client.get('/api/notes').json()['items']}
    assert 'tag' not in server.client.get('/api/tags').json()['tags']
    assert any(c['entity_id'] == nid and c['deleted'] and c['revision'] == revision + 3 for c in server.pull()['changes'])


def test_future_sync_schema_is_not_downgraded(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path}/future.db')
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE sync_identity (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            connection.exec_driver_sql("INSERT INTO sync_identity VALUES ('schema_version','2')")
        with pytest.raises(RuntimeError, match='refusing to downgrade'), engine.begin() as connection:
            upgrade(connection)
        with engine.connect() as connection:
            assert inspect(connection).get_table_names() == ['sync_identity']
            assert connection.exec_driver_sql('SELECT value FROM sync_identity').scalar_one() == '2'
    finally:
        engine.dispose()
