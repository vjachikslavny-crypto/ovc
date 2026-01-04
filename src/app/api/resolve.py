from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.block_models import YouTubeBlock, YouTubeData, dump_block
from app.db.models import generate_uuid


router = APIRouter(tags=["resolve"])

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_TIMECODE_RE = re.compile(
    r"^(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?$",
    re.IGNORECASE,
)


class YouTubeResolveRequest(BaseModel):
    url: str


class YouTubeResolveResponse(BaseModel):
    block: dict


def _extract_youtube_id(url: str) -> tuple[str, Optional[int]]:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        raise HTTPException(status_code=400, detail="Unsupported YouTube domain")

    video_id = None
    start_sec = None

    if host.endswith("youtu.be"):
        video_id = parsed.path.lstrip("/").split("/")[0]
        query = parse_qs(parsed.query or "")
        start_sec = _parse_start_param(query.get("t", [None])[0] or query.get("start", [None])[0])
    elif "youtube" in host:
        path = parsed.path or ""
        query = parse_qs(parsed.query or "")
        if path.startswith("/watch"):
            video_id = query.get("v", [None])[0]
            start_sec = _parse_start_param(
                query.get("t", [None])[0] or query.get("start", [None])[0] or parsed.fragment
            )
        elif path.startswith("/embed/") or path.startswith("/v/"):
            parts = [segment for segment in path.split("/") if segment]
            if len(parts) >= 2:
                video_id = parts[1]
            else:
                video_id = parts[-1] if parts else None
            start_sec = _parse_start_param(query.get("start", [None])[0] or query.get("t", [None])[0])
    elif "youtube-nocookie.com" in host:
        parts = [segment for segment in parsed.path.split("/") if segment]
        if len(parts) >= 2:
            video_id = parts[1]
        elif parts:
            video_id = parts[-1]
        start_sec = _parse_start_param(parse_qs(parsed.query or "").get("start", [None])[0])

    if not video_id or not _VIDEO_ID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="Unable to extract YouTube video id")

    return video_id, start_sec


def _parse_start_param(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    raw = raw.strip().lower()
    if raw.isdigit():
        return int(raw)
    match = _TIMECODE_RE.match(raw)
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total = hours * 3600 + minutes * 60 + seconds
    return total or None


@router.post("/resolve/youtube", response_model=YouTubeResolveResponse)
def resolve_youtube(payload: YouTubeResolveRequest):
    try:
        video_id, start_sec = _extract_youtube_id(payload.url)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    block = dump_block(
        YouTubeBlock(
            type="youtube",
            id=generate_uuid(),
            data=YouTubeData(videoId=video_id, startSec=start_sec),
        )
    )
    return YouTubeResolveResponse(block=block)
