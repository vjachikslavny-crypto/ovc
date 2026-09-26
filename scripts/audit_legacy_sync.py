#!/usr/bin/env python3
"""Read-only legacy outbox inventory; emits identifiers/counts, never content."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import sys

# Even config/model imports must not create files when this command is run.
sys.dont_write_bytecode = True
from local_data import current_paths, readonly


OPERATIONS = {"create_note", "update_note", "delete_note", "upload_file", "commit"}
NOTE_KEYS = ("localNoteId", "noteId", "fromId", "toId", "note_id", "from_id", "to_id")
FILE_KEYS = ("fileAssetId", "fileId", "file_id")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
QUARANTINE = "legacy_protocol_requires_manual_migration"


def safe_id(value):
    """Do not turn malformed ID fields into a channel for arbitrary private text."""
    if value is None:
        return None
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else "[redacted-invalid-id]"


def histogram(values):
    return dict(sorted(Counter(values).items()))


class Inventory:
    def __init__(self, db):
        self.db = db
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.columns = {
            table: {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')} if table in tables else set()
            for table in ("sync_outbox", "users", "notes", "files", "sync_note_map", "sync_entity_map")
        }

    def owner(self, uid):
        if uid is None:
            return {"exists": False, "active": None, "validity": "null"}
        if "id" not in self.columns["users"]:
            return {"exists": None, "active": None, "validity": "unverifiable"}
        active = '"is_active"' if "is_active" in self.columns["users"] else "NULL"
        row = self.db.execute(f'SELECT {active} FROM users WHERE id=?', (uid,)).fetchone()
        if row is None:
            return {"exists": False, "active": None, "validity": "missing"}
        state = "valid" if row[0] == 1 else "inactive" if row[0] == 0 else "unverifiable"
        return {"exists": True, "active": row[0] == 1 if row[0] is not None else None, "validity": state}

    def entity(self, kind, identifier, uid):
        table = "notes" if kind == "note" else "files"
        cols = self.columns[table]
        result = {"entity_type": kind, "id": safe_id(identifier), "exists": None,
                  "owner_id": None, "owner_validity": "unverifiable", "owner_matches_user": None,
                  "tombstone": None}
        if "id" not in cols:
            return result, None
        fields = [f'"{c}"' if c in cols else f'NULL AS "{c}"' for c in ("user_id", "tombstone", "note_id")]
        row = self.db.execute(f'SELECT {",".join(fields)} FROM "{table}" WHERE id=?', (identifier,)).fetchone()
        result["exists"] = row is not None
        if row is None:
            result["owner_validity"] = "entity_missing"
            return result, None
        owner = self.owner(row[0]) if "user_id" in cols else {"validity": "unverifiable"}
        result.update(owner_id=safe_id(row[0]), owner_validity=owner["validity"],
                      owner_matches_user=(row[0] == uid) if row[0] is not None and uid is not None else None,
                      tombstone=bool(row[1]) if row[1] is not None else None)
        if kind == "file":
            result["parent_note_id"] = safe_id(row[2])
        return result, row[2]

    def mappings(self, kind, identifier, item):
        legacy = {"state": "not_applicable", "remote_ids": [], "scope_proven": False}
        if kind == "note":
            cols = self.columns["sync_note_map"]
            legacy["state"] = "unavailable"
            if {"local_note_id", "remote_note_id"} <= cols:
                ids = [safe_id(r[0]) for r in self.db.execute(
                    "SELECT remote_note_id FROM sync_note_map WHERE local_note_id=? ORDER BY remote_note_id", (identifier,))]
                legacy.update(remote_ids=ids, state="unscoped" if ids else "absent")
        scoped = {"state": "unavailable", "candidates": [], "exact_scope_count": 0,
                  "remote_verified": False}
        required = {"user_id", "client_id", "remote_key", "entity_type", "local_id", "remote_id"}
        if required <= self.columns["sync_entity_map"]:
            complete = all(item.get(key) for key in ("user_id", "client_id", "remote_key"))
            for row in self.db.execute(
                "SELECT user_id,client_id,remote_key,remote_id FROM sync_entity_map "
                "WHERE entity_type=? AND local_id=? ORDER BY user_id,client_id,remote_key,remote_id", (kind, identifier)
            ):
                matches = [bool(item.get(k)) and row[i] == item[k]
                           for i, k in enumerate(("user_id", "client_id", "remote_key"))]
                scoped["candidates"].append({"remote_id": safe_id(row[3]),
                    "user_matches": matches[0], "client_matches": matches[1], "remote_matches": matches[2]})
                scoped["exact_scope_count"] += int(complete and all(matches))
            count = scoped["exact_scope_count"]
            scoped["state"] = ("scope_unproven" if not complete else "ambiguous" if count > 1
                               else "exact_scope_present" if count == 1 else "absent_in_scope")
        return {"legacy": legacy, "v1": scoped}


class References:
    """Inspect only legacy envelope fields; never serialize arbitrary payload keys."""
    def __init__(self):
        self.items = {}
        self.issues = set()
        self.block_states = []

    def add(self, kind, value, source, *, required=False):
        if value is None or value == "":
            if required:
                self.issues.add("required_reference_missing")
            return
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            self.issues.add("invalid_reference_id")
            return
        self.items.setdefault((kind, value), set()).add(source)

    def fields(self, obj, source):
        for key in NOTE_KEYS:
            self.add("note", obj.get(key), source + "." + key)
        for key in FILE_KEYS:
            self.add("file", obj.get(key), source + "." + key)

    def file_references(self, value, source):
        # Matches v1's local /files/<id>/... references without emitting URL/path.
        if isinstance(value, str) and value.startswith("/files/"):
            parts = value.split("/")
            if len(parts) > 3:
                self.add("file", parts[2], source, required=True)
        elif isinstance(value, dict):
            for key in FILE_KEYS:
                self.add("file", value.get(key), source)
            for child in value.values():
                self.file_references(child, source)
        elif isinstance(value, list):
            for child in value:
                self.file_references(child, source)

    def blocks(self, value, source):
        from app.agent.block_models import normalize_blocks
        try:
            normalized = normalize_blocks(value)
            self.block_states.append("valid" if normalized == value else "normalizable")
        except (ValueError, TypeError, RecursionError):
            # Validation messages may include complete note content.
            self.block_states.append("unsupported")
            self.issues.add("unsupported_blocks")
        self.file_references(value, source)

    def note(self, value, source):
        if not isinstance(value, dict):
            self.issues.add("invalid_legacy_shape")
            return
        self.add("note", value.get("id"), source + ".id")
        self.fields(value, source)
        if "blocks" in value:
            self.blocks(value["blocks"], source + ".blocks")
        for key in ("linksFrom", "linksTo", "files"):
            if key not in value:
                continue
            if not isinstance(value[key], list):
                self.issues.add("invalid_legacy_shape")
                continue
            for obj in value[key]:
                if not isinstance(obj, dict):
                    self.issues.add("invalid_legacy_shape")
                    continue
                self.fields(obj, source + "." + key)
                if key == "files":
                    self.add("file", obj.get("id"), source + ".files.id", required=True)

    def payload(self, item):
        try:
            payload = json.loads(item["payload_json"])
        except (ValueError, TypeError, RecursionError):
            self.issues.add("invalid_payload_json")
            return
        if not isinstance(payload, dict):
            self.issues.add("invalid_legacy_shape")
            return
        op = item["op_type"]
        self.fields(payload, "payload")
        if op in {"create_note", "update_note", "delete_note", "upload_file"}:
            self.add("note", payload.get("localNoteId"), "payload.localNoteId", required=True)
            if item.get("note_id") and payload.get("localNoteId") != item["note_id"]:
                self.issues.add("note_reference_mismatch")
        required = {"create_note": "note", "update_note": "patch"}.get(op)
        if required and not isinstance(payload.get(required), dict):
            self.issues.add("invalid_legacy_shape")
        for key in ("note", "patch", "snapshot"):
            if key in payload:
                self.note(payload[key], "payload." + key)
                if isinstance(payload[key], dict) and payload[key].get("id") and payload[key]["id"] != payload.get("localNoteId"):
                    self.issues.add("note_reference_mismatch")
        if op == "upload_file":
            self.add("file", payload.get("fileAssetId"), "payload.fileAssetId", required=True)
            if not isinstance(payload.get("filePath"), str) or not payload["filePath"]:
                self.issues.add("invalid_legacy_shape")
        if op == "commit":
            draft = payload.get("draft")
            if not isinstance(draft, list) or not draft:
                self.issues.add("invalid_legacy_shape")
                return
            for action in draft:
                if not isinstance(action, dict):
                    self.issues.add("invalid_legacy_shape")
                    continue
                self.fields(action, "payload.draft")
                kind = action.get("type")
                if not isinstance(kind, str):
                    kind = "unknown"
                keys = ("fromId", "toId") if kind == "add_link" else ("noteId",)
                for key in keys:
                    self.add("note", action.get(key), "payload.draft." + key, required=True)
                if kind == "insert_block":
                    self.blocks([action.get("block")], "payload.draft.block")
                elif kind == "update_block":
                    self.block_states.append("requires_context")
                    self.file_references(action.get("patch"), "payload.draft.patch")
                elif kind not in {"move_block", "add_tag", "remove_tag", "add_link", "set_style"}:
                    self.issues.add("unsupported_draft_action")


def inspect_row(inventory, item, has_protocol):
    refs = References()
    refs.add("note", item.get("note_id"), "outbox.note_id")
    if item.get("entity_id"):
        if item.get("entity_type") in {"note", "file"}:
            refs.add(item["entity_type"], item["entity_id"], "outbox.entity_id")
        else:
            refs.issues.add("unknown_entity_type")
    try:
        refs.payload(item)
    except RecursionError:
        refs.issues.add("payload_nesting_too_deep")
    uid = item.get("user_id")
    owner = inventory.owner(uid)
    reasons = {QUARANTINE} | refs.issues
    if owner["validity"] != "valid":
        reasons.add("outbox_owner_" + owner["validity"])
    if item["op_type"] not in OPERATIONS:
        reasons.add("unsupported_operation")
    for key in ("client_id", "remote_key"):
        if not item.get(key):
            reasons.add(key + "_missing")
    if item["op_type"] in {"update_note", "delete_note", "commit"} and item.get("base_revision") is None:
        reasons.add("base_revision_missing")
    if item["op_type"] == "commit":
        reasons.add("commit_requires_aggregate_rebuild")
    if item["op_type"] == "upload_file":
        reasons.add("upload_requires_content_hash_and_scoped_mapping")

    # Parent references are identifiers only; do not touch stored filesystem paths.
    entities = {}
    for kind, identifier in list(refs.items):
        entity, parent = inventory.entity(kind, identifier, uid)
        entities[kind, identifier] = entity
        if kind == "file":
            if parent:
                refs.add("note", parent, "files.note_id")
                parent_entity, _ = inventory.entity("note", parent, uid)
                if entity["owner_id"] != parent_entity["owner_id"]:
                    reasons.add("file_parent_owner_mismatch")
            if "payload.fileAssetId" in refs.items[kind, identifier]:
                targets = {key[1] for key, sources in refs.items.items() if "payload.localNoteId" in sources}
                if entity["exists"] and targets and parent not in targets:
                    reasons.add("file_parent_note_mismatch")
    reasons.update(refs.issues)
    for (kind, identifier), sources in sorted(refs.items.items()):
        entity = entities.get((kind, identifier))
        if entity is None:
            entity, _ = inventory.entity(kind, identifier, uid)
            entities[kind, identifier] = entity
        entity["sources"] = sorted(sources)
        entity["mappings"] = inventory.mappings(kind, identifier, item)
        if entity["exists"] is not True:
            reasons.add(kind + ("_missing" if entity["exists"] is False else "_unverifiable"))
        elif entity["owner_validity"] != "valid":
            reasons.add(kind + "_owner_" + entity["owner_validity"])
        if entity["owner_matches_user"] is False:
            reasons.add(kind + "_owner_mismatch")
        if entity["tombstone"]:
            reasons.add(kind + "_tombstoned")
        maps = entity["mappings"]
        if maps["legacy"]["state"] == "unscoped":
            reasons.add("legacy_mapping_unscoped")
        if maps["v1"]["state"] != "exact_scope_present":
            reasons.add("scoped_mapping_unproven")
    if not refs.items:
        reasons.add("no_entity_references")
    states = refs.block_states
    blocks = next((s for s in ("unsupported", "requires_context", "normalizable", "valid") if s in states), "not_present")
    return {
        "id": safe_id(item["id"]), "op_type": item["op_type"] if item["op_type"] in OPERATIONS else "unknown",
        "user_id": safe_id(uid), "user": owner, "status": "pending", "protocol_version": 0,
        "protocol_source": "column_missing" if not has_protocol else "null" if item["protocol_version"] is None else "zero",
        "entity_references": [entities[key] for key in sorted(entities)],
        "compatibility": {"v1": "incompatible_legacy_protocol", "queued_blocks": blocks},
        "decision": "quarantined_legacy", "quarantine_reason": QUARANTINE,
        "reasons": sorted(reasons), "automatic_migration_allowed": False,
    }


def audit(database):
    # mode=ro is in the shared helper; query_only is a second, connection-local guard.
    # BEGIN pins schema, queue and reference checks to one read snapshot, including WAL.
    with closing(readonly(database)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        inventory = Inventory(db)
        cols = inventory.columns["sync_outbox"]
        if not {"id", "op_type", "status", "payload_json"} <= cols:
            raise ValueError("Unsupported sync_outbox schema")
        fields = ("id", "op_type", "user_id", "note_id", "payload_json", "protocol_version",
                  "entity_type", "entity_id", "client_id", "remote_key", "base_revision")
        projection = ",".join(f'"{c}"' if c in cols else f'NULL AS "{c}"' for c in fields)
        has_protocol = "protocol_version" in cols
        predicate = " AND (protocol_version IS NULL OR protocol_version=0)" if has_protocol else ""
        rows = [inspect_row(inventory, dict(row), has_protocol) for row in db.execute(
            f"SELECT {projection} FROM sync_outbox WHERE status='pending'{predicate} ORDER BY id")]
        pending = db.execute("SELECT count(*) FROM sync_outbox WHERE status='pending'").fetchone()[0]
        entities = [e for row in rows for e in row["entity_references"]]
        summary = {
            "pending_total": pending, "pending_legacy": len(rows), "pending_nonlegacy": pending - len(rows),
            "quarantined_legacy": len(rows), "automatic_migration_allowed": 0,
            "by_operation": histogram(r["op_type"] for r in rows),
            "by_protocol_source": histogram(r["protocol_source"] for r in rows),
            "by_user_validity": histogram(r["user"]["validity"] for r in rows),
            "by_queued_blocks": histogram(r["compatibility"]["queued_blocks"] for r in rows),
            "by_reason": histogram(reason for row in rows for reason in row["reasons"]),
            "references": {kind: {
                "occurrences": sum(e["entity_type"] == kind for e in entities),
                "distinct_ids": len({e["id"] for e in entities if e["entity_type"] == kind}),
                "by_existence": histogram("present" if e["exists"] else "missing" if e["exists"] is False else "unverifiable"
                                          for e in entities if e["entity_type"] == kind),
                "by_owner_validity": histogram(e["owner_validity"] for e in entities if e["entity_type"] == kind),
                "by_legacy_mapping": histogram(e["mappings"]["legacy"]["state"] for e in entities if e["entity_type"] == kind),
                "by_v1_mapping": histogram(e["mappings"]["v1"]["state"] for e in entities if e["entity_type"] == kind),
            } for kind in ("note", "file")},
        }
        return {"report_version": 1, "read_only": True, "protocol_version_column_present": has_protocol,
                "summary": summary, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, help="Existing SQLite file (default: local_data config)")
    parser.add_argument("--summary-only", action="store_true", help="Omit the per-row inventory")
    args = parser.parse_args()
    try:
        report = audit(args.database if args.database is not None else current_paths()[0])
        if args.summary_only:
            del report["rows"]
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, sqlite3.Error, ValueError, RuntimeError, ImportError):
        # Never echo config values, payloads, paths, SQL parameters or validation input.
        print("ERROR: audit unavailable; check the existing SQLite file, schema and Python dependencies.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
