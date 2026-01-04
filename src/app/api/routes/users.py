from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.user import UserProfile, UserUpdate

router = APIRouter(tags=["users"])


def _serialize_user(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        username=user.username,
        email=user.email,
        isActive=user.is_active,
        role=user.role,
        displayName=user.display_name,
        avatarUrl=user.avatar_url,
    )


@router.get("/users/me", response_model=UserProfile)
def get_me(current_user: User = Depends(get_current_user)):
    return _serialize_user(current_user)


@router.patch("/users/me", response_model=UserProfile)
def update_me(payload: UserUpdate, current_user: User = Depends(get_current_user)):
    with get_session() as session:
        user = session.get(User, current_user.id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if payload.display_name is not None:
            user.display_name = payload.display_name.strip() or None
        if payload.avatar_url is not None:
            user.avatar_url = payload.avatar_url.strip() or None
        session.add(user)
        session.flush()
        session.refresh(user)
        return _serialize_user(user)

