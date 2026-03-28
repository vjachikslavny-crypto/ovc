from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.config import settings
from app.core.security import get_bearer_token, get_current_user
from app.models.user import User
from app.services.sync_engine import get_sync_status, trigger_sync_now

router = APIRouter(tags=["sync"])


@router.get("/sync/status")
def sync_status(current_user: User = Depends(get_current_user)):
    status = get_sync_status(user_id=current_user.id)
    status["requestedByUserId"] = current_user.id
    return status


@router.post("/sync/trigger")
def sync_trigger(request: Request, current_user: User = Depends(get_current_user)):
    if settings.sync_mode in {"off", "shared-db"}:
        return {"ok": False, "reason": f"sync_mode_{settings.sync_mode}"}
    if not settings.sync_remote_base_url:
        return {"ok": False, "reason": "remote_base_url_empty"}
    bearer = get_bearer_token(request)
    return trigger_sync_now(access_token=bearer, user_id=current_user.id)
