from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserProfile(BaseModel):
    id: str
    username: str
    email: Optional[EmailStr] = None
    is_active: bool = Field(alias="isActive")
    role: str
    display_name: Optional[str] = Field(default=None, alias="displayName")
    avatar_url: Optional[str] = Field(default=None, alias="avatarUrl")


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, alias="displayName")
    avatar_url: Optional[str] = Field(default=None, alias="avatarUrl")
