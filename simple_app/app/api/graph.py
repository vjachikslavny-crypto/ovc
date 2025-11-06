from __future__ import annotations

import json
import hashlib
from typing import Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import GroupPreference, Note, NoteLink
from app.db.session import get_session
from app.utils.layout_hints import parse_layout_hints

router = APIRouter(tags=["graph"])


DEFAULT_COLOR = "#8b5cf6"
DEFAULT_LABEL = "Без группы"


class GroupColorRequest(BaseModel):
    color: str = Field(..., min_length=4, max_length=16)


class GroupLabelRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)


@router.get("/graph")
async def graph_endpoint():
    with get_session() as session:
        notes = session.execute(select(Note)).scalars().all()
        links = session.execute(select(NoteLink)).scalars().all()
        groups, assignments = _build_groups(session, notes, links)

        nodes: List[dict] = []
        for note in notes:
            group_key = assignments.get(note.id, "default")
            group_meta = groups.get(group_key, groups["default"])
            blocks = json.loads(note.blocks_json or "[]")
            flat_text = _blocks_to_text(blocks)
            layout_hints = parse_layout_hints(note.layout_hints)
            size_weight = layout_hints.get("sizeWeight", 1.0)
            base_size = max(0.4, min(3.0, len(flat_text) / 400.0 + len(blocks) / 8.0))
            size_score = max(0.3, min(6.0, base_size * size_weight))

            nodes.append(
                {
                    "id": note.id,
                    "title": note.title,
                    "group_key": group_key,
                    "group_label": group_meta["label"],
                    "color": group_meta["color"],
                    "blockCount": len(blocks),
                    "textSize": len(flat_text),
                    "sizeScore": size_score,
                    "layoutHints": layout_hints,
                    "sizeWeight": size_weight,
                    "tags": [tag.tag for tag in note.tags],
                    "updatedAt": note.updated_at.isoformat(),
                }
            )

        edges = [
            {
                "id": link.id,
                "source": link.from_id,
                "target": link.to_id,
                "reason": link.reason,
                "confidence": link.confidence,
            }
            for link in links
        ]

    return {"nodes": nodes, "edges": edges}


@router.get("/graph/groups")
async def graph_groups():
    with get_session() as session:
        notes = session.execute(select(Note)).scalars().all()
        links = session.execute(select(NoteLink)).scalars().all()
        groups, _ = _build_groups(session, notes, links)

    payload = [
        {
            "key": key,
            "label": meta["label"],
            "color": meta["color"],
            "count": len(meta["note_ids"]),
        }
        for key, meta in groups.items()
    ]
    payload.sort(key=lambda item: (item["key"] != "default", item["label"]))
    return {"groups": payload}


@router.post("/graph/groups/{cluster}")
async def update_group_color(cluster: str, payload: GroupColorRequest):
    key = cluster.strip() or "default"

    with get_session() as session:
        pref = (
            session.execute(select(GroupPreference).where(GroupPreference.key == key))
            .scalars()
            .first()
        )
        if not pref:
            pref = GroupPreference(key=key, label=DEFAULT_LABEL, color=payload.color)
        else:
            pref.color = payload.color
        session.add(pref)

    return {"cluster": key, "color": payload.color}


@router.post("/graph/groups/{cluster}/label")
async def update_group_label(cluster: str, payload: GroupLabelRequest):
    key = cluster.strip() or "default"
    label = payload.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="Label cannot be empty")

    with get_session() as session:
        pref = (
            session.execute(select(GroupPreference).where(GroupPreference.key == key))
            .scalars()
            .first()
        )
        if not pref:
            pref = GroupPreference(key=key, label=label, color=DEFAULT_COLOR)
        else:
            pref.label = label
        session.add(pref)

    return {"cluster": key, "label": label}


def _build_groups(
    session, notes: List[Note], links: List[NoteLink]
) -> Tuple[Dict[str, dict], Dict[str, str]]:
    prefs = {
        pref.key: pref
        for pref in session.execute(select(GroupPreference)).scalars().all()
    }

    manual_groups: Dict[str, dict] = {}
    assignments: Dict[str, str] = {}

    for note in notes:
        passport = _load_json(note.passport_json)
        group_info = passport.get("group")
        if isinstance(group_info, dict):
            raw_key = group_info.get("key") or group_info.get("id") or group_info.get("slug")
            label = group_info.get("label") or group_info.get("name") or raw_key
        elif isinstance(group_info, str):
            raw_key = group_info
            label = raw_key
        else:
            raw_key = None
            label = None

        if raw_key:
            cluster_key = f"manual:{raw_key.strip()}"
            entry = manual_groups.setdefault(
                cluster_key,
                {
                    "key": cluster_key,
                    "label": label or raw_key,
                    "color": DEFAULT_COLOR,
                    "note_ids": [],
                },
            )
            entry["note_ids"].append(note.id)
            assignments[note.id] = cluster_key

    candidate_ids: Set[str] = {note.id for note in notes if note.id not in assignments}
    adjacency: Dict[str, Set[str]] = {note.id: set() for note in notes}
    for link in links:
        adjacency.setdefault(link.from_id, set()).add(link.to_id)
        adjacency.setdefault(link.to_id, set()).add(link.from_id)

    visited: Set[str] = set()
    component_groups: Dict[str, dict] = {}

    for note_id in candidate_ids:
        if note_id in visited:
            continue
        stack = [note_id]
        component: List[str] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor in candidate_ids and neighbor not in visited:
                    stack.append(neighbor)
        if len(component) > 1:
            digest = hashlib.sha1("::".join(sorted(component)).encode()).hexdigest()[:12]
            key = f"component:{digest}"
            entry = {
                "key": key,
                "label": f"Связка {component[0][:6]}",
                "color": DEFAULT_COLOR,
                "note_ids": sorted(component),
            }
            component_groups[key] = entry
            for nid in component:
                assignments[nid] = key

    default_ids = sorted([note.id for note in notes if assignments.get(note.id) is None])

    groups: Dict[str, dict] = {**manual_groups, **component_groups}
    groups["default"] = {
        "key": "default",
        "label": DEFAULT_LABEL,
        "color": DEFAULT_COLOR,
        "note_ids": default_ids,
    }
    for nid in default_ids:
        assignments[nid] = "default"

    for key, meta in groups.items():
        pref = prefs.get(key)
        if pref:
            meta["label"] = pref.label or meta["label"]
            meta["color"] = pref.color or meta["color"]

    return groups, assignments


def _load_json(value: Optional[str]) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _blocks_to_text(blocks: List[dict]) -> str:
    lines: List[str] = []
    for block in blocks:
        b_type = block.get("type")
        data = block.get("data", {})
        if b_type == "heading":
            lines.append(str(data.get("text", "")))
        elif b_type == "paragraph":
            parts = data.get("parts", [])
            if not parts:
                lines.append(str(data.get("text", "")))
            else:
                lines.append("".join(part.get("text", "") for part in parts))
        elif b_type in {"bulletList", "numberList"}:
            for item in data.get("items", []):
                if isinstance(item, dict):
                    lines.append(item.get("text", ""))
                else:
                    lines.append(str(item))
        elif b_type == "quote":
            lines.append(str(data.get("text", "")))
        elif b_type == "table":
            for row in data.get("rows", []):
                if isinstance(row, list):
                    lines.append(" ".join(str(cell) for cell in row))
        elif b_type == "source":
            lines.append(str(data.get("title", "")))
            if data.get("summary"):
                lines.append(str(data.get("summary")))
        elif b_type == "summary":
            lines.append(str(data.get("text", "")))
        elif b_type == "todo":
            for item in data.get("items", []):
                if isinstance(item, dict):
                    lines.append(item.get("text", ""))
    return "\n".join(line for line in lines if line)
