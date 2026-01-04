from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request

from app.models.audit import AuditLog


def log_event(
    session,
    event: str,
    *,
    user_id: Optional[str] = None,
    request: Optional[Request] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    ip = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None
    entry = AuditLog(
        user_id=user_id,
        event=event,
        ip=ip,
        user_agent=user_agent,
        event_meta=metadata or {},
    )
    session.add(entry)
