from __future__ import annotations

import datetime as dt
import hashlib
from typing import Dict, List, Set, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.models import GroupPreference, Note, NoteLink
from app.db.session import get_session

router = APIRouter(tags=["graph"])


class GroupColorRequest(BaseModel):
    color: str = Field(..., min_length=4, max_length=16)


class GroupLabelRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)


DEFAULT_COLOR = "#8b5cf6"
DEFAULT_LABEL = "Без группы"


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
            nodes.append(
                {
                    "id": note.id,
                    "title": note.title,
                    "importance": note.importance,
                    "cluster": note.cluster,
                    "cluster_color": group_meta["color"],
                    "group_key": group_key,
                    "group_label": group_meta["label"],
                    "priority": note.priority,
                    "status": note.status,
                    "tags": [tag.tag for tag in note.tags],
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
    payload = []
    for key, meta in groups.items():
        payload.append(
            {
                "key": key,
                "label": meta["label"],
                "color": meta["color"],
                "count": len(meta["note_ids"]),
            }
        )
    payload.sort(key=lambda item: (item["key"] != "default", item["label"]))
    return {"groups": payload}


@router.post("/graph/groups/{cluster}")
async def update_group_color(cluster: str, payload: GroupColorRequest):
    group_key = cluster.strip() or "default"

    with get_session() as session:
        notes = session.execute(select(Note)).scalars().all()
        links = session.execute(select(NoteLink)).scalars().all()
        groups, _ = _build_groups(session, notes, links)

        meta = groups.get(group_key)
        if not meta:
            raise HTTPException(status_code=404, detail="Group not found")

        pref = session.execute(select(GroupPreference).where(GroupPreference.key == group_key)).scalar_one_or_none()
        if pref:
            pref.color = payload.color
            pref.updated_at = dt.datetime.utcnow()
        else:
            pref = GroupPreference(key=group_key, label=meta["label"], color=payload.color)
        session.add(pref)

        for note_id in meta["note_ids"]:
            note = session.get(Note, note_id)
            if note:
                note.cluster_color = payload.color
                session.add(note)

        meta["color"] = payload.color

    return {"cluster": group_key, "color": payload.color, "count": len(meta["note_ids"])}


@router.post("/graph/groups/{cluster}/label")
async def update_group_label(cluster: str, payload: GroupLabelRequest):
    group_key = cluster.strip() or "default"
    new_label = payload.label.strip()
    if not new_label:
        raise HTTPException(status_code=422, detail="Label cannot be empty")

    with get_session() as session:
        notes = session.execute(select(Note)).scalars().all()
        links = session.execute(select(NoteLink)).scalars().all()
        groups, _ = _build_groups(session, notes, links)

        meta = groups.get(group_key)
        if not meta:
            raise HTTPException(status_code=404, detail="Group not found")

        pref = session.execute(select(GroupPreference).where(GroupPreference.key == group_key)).scalar_one_or_none()
        if not pref:
            pref = GroupPreference(key=group_key, label=new_label, color=meta["color"])
        else:
            pref.label = new_label
            pref.updated_at = dt.datetime.utcnow()
        session.add(pref)

    return {"cluster": group_key, "label": new_label}


def _build_groups(session, notes: List[Note], links: List[NoteLink]) -> Tuple[Dict[str, dict], Dict[str, str]]:
    prefs = {
        pref.key: pref
        for pref in session.execute(select(GroupPreference)).scalars().all()
    }
    notes_by_id: Dict[str, Note] = {note.id: note for note in notes}
    manual_groups: Dict[str, dict] = {}
    manual_note_ids: Set[str] = set()
    assignments: Dict[str, str] = {}

    for note in notes:
        cluster_name = _normalize_cluster(note.cluster)
        if cluster_name and cluster_name.lower() != "default":
            key = f"cluster:{cluster_name}"
            entry = manual_groups.setdefault(
                key,
                {
                    "key": key,
                    "label": cluster_name,
                    "color": note.cluster_color or DEFAULT_COLOR,
                    "note_ids": [],
                },
            )
            if entry["color"] == DEFAULT_COLOR and note.cluster_color:
                entry["color"] = note.cluster_color
            entry["note_ids"].append(note.id)
            assignments[note.id] = key
            manual_note_ids.add(note.id)

    candidate_ids: Set[str] = {note.id for note in notes if note.id not in manual_note_ids}
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
            sorted_ids = sorted(component)
            digest = hashlib.sha1("::".join(sorted_ids).encode("utf-8")).hexdigest()[:12]
            key = f"component:{digest}"
            label_source = notes_by_id[sorted_ids[0]]
            label = label_source.title or f"Связка {sorted_ids[0][:6]}"
            color = next(
                (notes_by_id[nid].cluster_color for nid in component if notes_by_id[nid].cluster_color),
                DEFAULT_COLOR,
            )
            component_groups[key] = {
                "key": key,
                "label": label,
                "color": color,
                "note_ids": sorted_ids,
            }
            for nid in component:
                assignments[nid] = key

    default_ids = sorted([note.id for note in notes if assignments.get(note.id) is None])
    default_color = next(
        (notes_by_id[nid].cluster_color for nid in default_ids if notes_by_id[nid].cluster_color),
        DEFAULT_COLOR,
    )

    groups = {**manual_groups, **component_groups}
    groups["default"] = {
        "key": "default",
        "label": DEFAULT_LABEL,
        "color": default_color,
        "note_ids": default_ids,
    }
    for nid in default_ids:
        assignments[nid] = "default"

    # reconcile with stored preferences
    for key, meta in groups.items():
        meta["note_ids"] = sorted(meta["note_ids"])
        pref = prefs.get(key)
        if not pref:
            pref = GroupPreference(key=key, label=meta["label"], color=meta["color"])
            session.add(pref)
            session.flush()
        meta["label"] = pref.label or meta["label"]
        meta["color"] = pref.color or meta["color"]

    return groups, assignments


def _normalize_cluster(value: str | None) -> str:
    return (value or "").strip()
