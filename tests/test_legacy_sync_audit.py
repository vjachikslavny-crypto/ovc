"""Run directly with unittest: the repository pytest fixture starts the app."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import audit_legacy_sync as audit_tool


class LegacyAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ovc-legacy-audit-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "database with #?.sqlite"
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                CREATE TABLE users (id TEXT PRIMARY KEY, is_active INTEGER);
                CREATE TABLE notes (id TEXT PRIMARY KEY, user_id TEXT, tombstone INTEGER);
                CREATE TABLE files (id TEXT PRIMARY KEY, user_id TEXT, note_id TEXT);
                CREATE TABLE sync_outbox (id TEXT PRIMARY KEY, op_type TEXT, user_id TEXT,
                    note_id TEXT, payload_json TEXT, status TEXT DEFAULT 'pending');
                CREATE TABLE sync_note_map (local_note_id TEXT, remote_note_id TEXT);
                INSERT INTO users VALUES ('owner',1),('other',1),('inactive',0);
                INSERT INTO notes VALUES ('note','owner',0),('other-note','other',0),
                    ('orphan',NULL,0),('dangling','gone',0),('deleted','owner',1);
                INSERT INTO files VALUES ('file','owner','note'),('wrong-file','other','note');
            """)

    def add(self, identifier, op="update_note", *, uid="owner", note="note", payload=None, status="pending", protocol=None):
        if payload is None:
            payload = {"localNoteId": note, "patch": {"blocks": []}}
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO sync_outbox(id,op_type,user_id,note_id,payload_json,status) VALUES (?,?,?,?,?,?)",
                       (identifier, op, uid, note, raw, status))
            if protocol is not None:
                db.execute("UPDATE sync_outbox SET protocol_version=? WHERE id=?", (protocol, identifier))

    def upgrade_fixture(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                ALTER TABLE sync_outbox ADD COLUMN protocol_version INTEGER;
                ALTER TABLE sync_outbox ADD COLUMN client_id TEXT;
                ALTER TABLE sync_outbox ADD COLUMN remote_key TEXT;
                ALTER TABLE sync_outbox ADD COLUMN base_revision INTEGER;
                ALTER TABLE sync_outbox ADD COLUMN entity_type TEXT;
                ALTER TABLE sync_outbox ADD COLUMN entity_id TEXT;
                CREATE TABLE sync_entity_map (user_id TEXT, client_id TEXT, remote_key TEXT,
                    entity_type TEXT, local_id TEXT, remote_id TEXT);
            """)

    def test_legacy_selection_and_no_writes_or_app_imports(self):
        self.add("pending")
        self.add("failed", status="failed")
        self.add("done", status="done")
        before = hashlib.sha256(self.path.read_bytes()).digest()
        files_before = set(Path(self.tmp.name).iterdir())
        imported_before = set(sys.modules)
        report = audit_tool.audit(self.path)
        self.assertEqual([r["id"] for r in report["rows"]], ["pending"])
        self.assertEqual(report["summary"]["pending_legacy"], 1)
        self.assertEqual(report["rows"][0]["protocol_source"], "column_missing")
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).digest())
        self.assertEqual(files_before, set(Path(self.tmp.name).iterdir()))
        self.assertFalse({'app.main', 'app.db.session'} & (set(sys.modules) - imported_before))
        with closing(audit_tool.readonly(self.path)) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM sync_outbox")
        missing = Path(self.tmp.name) / "missing.db"
        with self.assertRaises(sqlite3.OperationalError):
            audit_tool.audit(missing)
        self.assertFalse(missing.exists())

    def test_zero_null_versions_and_exact_scope_never_allow_migration(self):
        self.upgrade_fixture()
        self.add("zero", protocol=0)
        self.add("null")
        self.add("v1", protocol=1)
        self.add("future", protocol=2)
        self.add("failed", protocol=0, status="failed")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE sync_outbox SET client_id='client',remote_key='private-remote',base_revision=7 WHERE id='zero'")
            db.executemany("INSERT INTO sync_entity_map VALUES (?,?,?,?,?,?)", [
                ('owner', 'client', 'private-remote', 'note', 'note', 'remote-note'),
                ('other', 'client', 'private-remote', 'note', 'note', 'other-remote'),
                ('owner', 'wrong-client', 'private-remote', 'note', 'note', 'wrong-client-remote'),
                ('owner', 'client', 'wrong-remote', 'note', 'note', 'wrong-peer-remote')])
        report = audit_tool.audit(self.path)
        self.assertEqual(report["summary"]["pending_total"], 4)
        self.assertEqual(report["summary"]["pending_legacy"], 2)
        self.assertEqual(report["summary"]["by_protocol_source"], {"zero": 1, "null": 1})
        null, zero = report["rows"]
        self.assertEqual(null["entity_references"][0]["mappings"]["v1"]["state"], "scope_unproven")
        mapping = zero["entity_references"][0]["mappings"]["v1"]
        self.assertEqual(mapping["exact_scope_count"], 1)
        self.assertEqual(len(mapping["candidates"]), 4)
        self.assertEqual(zero["decision"], "quarantined_legacy")
        self.assertFalse(zero["automatic_migration_allowed"])
        self.assertIn(audit_tool.QUARANTINE, zero["reasons"])
        self.assertNotIn('private-remote', json.dumps(report))

    def test_references_ownership_links_files_and_legacy_mappings(self):
        self.add("references", payload={"localNoteId": "note", "patch": {}, "snapshot": {
            "id": "note", "blocks": [{"type": "image", "data": {"src": "/files/wrong-file/original?private-token"}}],
            "linksFrom": [{"fromId": "note", "toId": "other-note"}],
            "linksTo": [{"fromId": "missing-note", "toId": "note"}],
            "files": [{"id": "file"}]}})
        self.add("commit", "commit", note=None, payload={"draft": [
            {"type": "add_link", "fromId": "orphan", "toId": "dangling"},
            {"type": "update_block", "noteId": "deleted", "patch": {"src": "/files/gone/original"}}]})
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO sync_note_map VALUES ('note','remote-note')")
        rows = {r["id"]: r for r in audit_tool.audit(self.path)["rows"]}
        refs = {(r["entity_type"], r["id"]): r for r in rows["references"]["entity_references"]}
        self.assertEqual(set(refs), {('note','note'), ('note','other-note'), ('note','missing-note'),
                                     ('file','file'), ('file','wrong-file')})
        self.assertFalse(refs['note', 'other-note']["owner_matches_user"])
        self.assertFalse(refs['note', 'missing-note']["exists"])
        self.assertEqual(refs['note', 'note']["mappings"]["legacy"]["state"], "unscoped")
        self.assertIn("file_parent_owner_mismatch", rows["references"]["reasons"])
        self.assertTrue({"note_owner_null", "note_owner_missing", "note_tombstoned", "file_missing"}
                        <= set(rows["commit"]["reasons"]))

    def test_upload_mismatched_parent_deleted_note_and_invalid_users(self):
        self.add("upload", "upload_file", note="other-note", payload={
            "localNoteId": "other-note", "fileAssetId": "file", "filePath": "/private/do-not-read"})
        self.add("delete", "delete_note", note=None, payload={"localNoteId": "missing"})
        for uid in (None, "gone", "inactive"):
            self.add("user-" + str(uid), uid=uid)
        report = audit_tool.audit(self.path)
        rows = {r["id"]: r for r in report["rows"]}
        self.assertIn("file_parent_note_mismatch", rows["upload"]["reasons"])
        self.assertIn("note_missing", rows["delete"]["reasons"])
        self.assertEqual(report["summary"]["by_user_validity"], {"valid": 2, "null": 1, "missing": 1, "inactive": 1})

    def test_malformed_data_is_reported_without_private_content(self):
        secret = "private content https://secret.invalid/?token=never-print"
        self.add("json", payload=secret)
        self.add("list", payload=[])
        self.add("blocks", payload={"localNoteId": "note", "patch": {"blocks": [
            {"type": "unknown-private-type", "data": {"text": secret}}]}, "token": secret})
        self.add("shape", "commit", note=None, payload={"draft": [None, {"type": [], "noteId": secret}]})
        self.add("unknown", secret, payload={"arbitrary-private-key": secret})
        self.add("missing-ref", payload={"patch": {}})
        self.add("mismatch", payload={"localNoteId": "other-note", "patch": {}})
        report = audit_tool.audit(self.path)
        output = json.dumps(report)
        for text in (secret, "arbitrary-private-key", "unknown-private-type"):
            self.assertNotIn(text, output)
        reasons = report["summary"]["by_reason"]
        for reason in ("invalid_payload_json", "invalid_legacy_shape", "unsupported_blocks", "invalid_reference_id",
                       "unsupported_operation", "required_reference_missing", "note_reference_mismatch"):
            self.assertIn(reason, reasons)
        self.assertEqual(report["summary"]["quarantined_legacy"], 7)

    def test_missing_optional_schema_is_unverifiable_and_empty_queue_is_valid(self):
        self.assertEqual(audit_tool.audit(self.path)["summary"]["pending_legacy"], 0)
        self.add("pending")
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("DROP TABLE notes; DROP TABLE users; DROP TABLE sync_note_map;")
        row = audit_tool.audit(self.path)["rows"][0]
        self.assertEqual(row["user"]["validity"], "unverifiable")
        self.assertIsNone(row["entity_references"][0]["exists"])
        self.assertEqual(row["entity_references"][0]["mappings"]["legacy"]["state"], "unavailable")

    def test_reads_uncheckpointed_wal_and_uses_one_snapshot(self):
        with closing(sqlite3.connect(self.path)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            self.add("wal-row")
            original = audit_tool.Inventory.owner
            changed = False

            def concurrent_change(inventory, uid):
                nonlocal changed
                if not changed:
                    writer.execute("UPDATE notes SET user_id='other' WHERE id='note'")
                    writer.commit()
                    changed = True
                return original(inventory, uid)

            with patch.object(audit_tool.Inventory, "owner", concurrent_change):
                report = audit_tool.audit(self.path)
            self.assertEqual(report["summary"]["pending_legacy"], 1)
            self.assertTrue(report["rows"][0]["entity_references"][0]["owner_matches_user"])
            self.assertEqual(writer.execute("SELECT user_id FROM notes WHERE id='note'").fetchone()[0], "other")

    def test_cli_summary_and_sanitized_errors(self):
        self.add("pending")
        command = [sys.executable, "-B", str(ROOT / "scripts" / "audit_legacy_sync.py"), "--database"]
        result = subprocess.run(command + [str(self.path), "--summary-only"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("rows", json.loads(result.stdout))
        result = subprocess.run(command + [str(self.path)], capture_output=True, text=True)
        self.assertEqual(len(json.loads(result.stdout)["rows"]), 1)
        result = subprocess.run(command + [str(Path(self.tmp.name) / "private-secret.db")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("private-secret", result.stderr)
        self.assertFalse(result.stdout)


if __name__ == "__main__":
    unittest.main()
