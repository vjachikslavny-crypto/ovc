from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.models import Note, SyncNoteMap, SyncOutbox
from app.db import session as db_session
from app.models.user import User  # noqa: F401
from app.models.session import RefreshToken  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.services import sync_engine


class _FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self):
        self._notes = {}
        self._idx = 0

    def post(self, path, json=None, headers=None, files=None):
        if path.startswith("/api/notes"):
            self._idx += 1
            remote_id = f"remote-{self._idx}"
            self._notes[remote_id] = dict(json or {})
            self._notes[remote_id]["id"] = remote_id
            return _FakeResponse(201, self._notes[remote_id])
        return _FakeResponse(404, text="not found")

    def patch(self, path, json=None):
        remote_id = path.split("/")[-1]
        if remote_id not in self._notes:
            return _FakeResponse(404, text="not found")
        self._notes[remote_id].update(json or {})
        return _FakeResponse(200, self._notes[remote_id])

    def delete(self, path):
        remote_id = path.split("/")[-1]
        self._notes.pop(remote_id, None)
        return _FakeResponse(200, {"ok": True})

    def get(self, path):
        if path.startswith("/api/notes?"):
            items = [
                {
                    "id": note_id,
                    "title": payload.get("title", ""),
                    "styleTheme": payload.get("styleTheme", "clean"),
                    "createdAt": "2025-01-01T00:00:00",
                    "updatedAt": "2025-01-01T00:00:00",
                }
                for note_id, payload in self._notes.items()
            ]
            return _FakeResponse(200, {"items": items, "total": len(items)})

        if path.startswith("/api/notes/"):
            note_id = path.split("/")[-1]
            payload = self._notes.get(note_id)
            if not payload:
                return _FakeResponse(404, text="not found")
            detail = {
                "id": note_id,
                "title": payload.get("title", ""),
                "styleTheme": payload.get("styleTheme", "clean"),
                "createdAt": "2025-01-01T00:00:00",
                "updatedAt": "2025-01-01T00:00:00",
                "layoutHints": payload.get("layoutHints", {}),
                "blocks": payload.get("blocks", []),
                "passport": payload.get("passport", {}),
                "tags": [],
                "linksFrom": [],
                "linksTo": [],
                "sources": [],
            }
            return _FakeResponse(200, detail)

        return _FakeResponse(404, text="not found")

    def post_upload(self, path, files=None, headers=None):
        return _FakeResponse(200, {"ok": True})


class SyncEngineTests(unittest.TestCase):
    def setUp(self):
        self._old_sync_enabled = settings.sync_enabled
        self._old_remote = settings.sync_remote_base_url
        self._old_pull = settings.sync_pull_enabled
        self._old_batch = settings.sync_batch_size

        settings.sync_enabled = True
        settings.sync_remote_base_url = "https://sync.test"
        settings.sync_pull_enabled = False
        settings.sync_batch_size = 100

        self._tmp = tempfile.TemporaryDirectory()
        test_engine = create_engine(f"sqlite:///{self._tmp.name}/sync-tests.db")
        SessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False)

        self._old_engine = db_session.engine
        self._old_session_local = db_session.SessionLocal

        db_session.engine = test_engine
        db_session.SessionLocal = SessionLocal

        Base.metadata.create_all(bind=test_engine)

    def tearDown(self):
        db_session.engine = self._old_engine
        db_session.SessionLocal = self._old_session_local
        settings.sync_enabled = self._old_sync_enabled
        settings.sync_remote_base_url = self._old_remote
        settings.sync_pull_enabled = self._old_pull
        settings.sync_batch_size = self._old_batch
        self._tmp.cleanup()

    def test_outbox_retry_stops_on_retryable_error(self):
        with db_session.get_session() as session:
            for idx in range(3):
                session.add(
                    SyncOutbox(
                        op_type=sync_engine.OP_UPDATE_NOTE,
                        note_id=f"note-{idx}",
                        payload_json="{}",
                        status=sync_engine.STATUS_PENDING,
                    )
                )

        with db_session.get_session() as session:
            with patch("app.services.sync_engine._flush_operation") as flush:
                flush.side_effect = [None, sync_engine.RetryableSyncError("network down"), None]
                pushed, failed = sync_engine._push_outbox(session, _FakeClient())

                self.assertEqual(pushed, 1)
                self.assertEqual(failed, 1)

                rows = session.execute(select(SyncOutbox).order_by(SyncOutbox.created_at.asc())).scalars().all()
                self.assertEqual(rows[0].status, sync_engine.STATUS_DONE)
                self.assertEqual(rows[1].status, sync_engine.STATUS_FAILED)
                self.assertEqual(rows[1].tries, 1)
                self.assertEqual(rows[2].status, sync_engine.STATUS_PENDING)

    def test_smoke_offline_create_then_update_then_sync(self):
        local_note_id = "local-note-1"

        with db_session.get_session() as session:
            session.add(
                Note(
                    id=local_note_id,
                    title="Offline title",
                    style_theme="clean",
                    layout_hints="{}",
                    blocks_json="[]",
                    passport_json="{}",
                )
            )
            sync_engine.enqueue_sync_operation(
                session,
                sync_engine.OP_CREATE_NOTE,
                {
                    "localNoteId": local_note_id,
                    "note": {
                        "title": "Offline title",
                        "styleTheme": "clean",
                        "layoutHints": {},
                        "blocks": [],
                        "passport": {},
                    },
                },
                note_id=local_note_id,
            )
            sync_engine.enqueue_sync_operation(
                session,
                sync_engine.OP_UPDATE_NOTE,
                {
                    "localNoteId": local_note_id,
                    "patch": {"title": "Edited offline title"},
                    "snapshot": {
                        "title": "Edited offline title",
                        "styleTheme": "clean",
                        "layoutHints": {},
                        "blocks": [],
                        "passport": {},
                    },
                },
                note_id=local_note_id,
            )

        fake_client = _FakeClient()
        with patch("app.services.sync_engine._build_client", return_value=fake_client):
            result = sync_engine.trigger_sync_now()
            self.assertTrue(result["ok"])
            self.assertEqual(result["pushed"], 2)

        with db_session.get_session() as session:
            map_row = session.get(SyncNoteMap, local_note_id)
            self.assertIsNotNone(map_row)

            outbox_rows = session.execute(select(SyncOutbox)).scalars().all()
            self.assertTrue(all(row.status == sync_engine.STATUS_DONE for row in outbox_rows))

            remote_payload = fake_client._notes.get(map_row.remote_note_id)
            self.assertIsNotNone(remote_payload)
            self.assertEqual(remote_payload.get("title"), "Edited offline title")

    def test_upload_waits_for_note_mapping(self):
        with db_session.get_session() as session:
            session.add(
                SyncOutbox(
                    op_type=sync_engine.OP_CREATE_NOTE,
                    note_id="note-upload",
                    payload_json="{}",
                    status=sync_engine.STATUS_PENDING,
                )
            )
            session.flush()

            with self.assertRaises(sync_engine.RetryableSyncError):
                sync_engine._flush_upload_file(
                    session,
                    _FakeClient(),
                    {
                        "localNoteId": "note-upload",
                        "filePath": "/tmp/not-used",
                        "filename": "a.txt",
                        "mime": "text/plain",
                    },
                )


if __name__ == "__main__":
    unittest.main()
