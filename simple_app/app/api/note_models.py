from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agent.block_models import BlockModel

try:
    from pydantic import ConfigDict
except ImportError:  # Pydantic v1
    ConfigDict = None


class _BaseModel(BaseModel):
    if ConfigDict is not None:  # pragma: no branch - runtime switch
        model_config = ConfigDict(populate_by_name=True)
    else:
        class Config:
            allow_population_by_field_name = True

class LinkPayload(_BaseModel):
    id: str
    from_id: str = Field(alias="fromId")
    to_id: str = Field(alias="toId")
    title: str
    reason: Optional[str]
    confidence: Optional[float]


class SourcePayload(_BaseModel):
    id: str
    url: str
    title: str
    domain: str
    published_at: Optional[str]
    summary: Optional[str]


class NoteSummary(_BaseModel):
    id: str
    title: str
    style_theme: str = Field(alias="styleTheme")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class NoteDetail(NoteSummary):
    blocks: List[Dict[str, Any]]
    layout_hints: Dict[str, Any] = Field(default_factory=dict, alias="layoutHints")
    passport: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    links_from: List[LinkPayload] = Field(default_factory=list, alias="linksFrom")
    links_to: List[LinkPayload] = Field(default_factory=list, alias="linksTo")
    sources: List[SourcePayload] = Field(default_factory=list)


class NoteListResponse(_BaseModel):
    items: List[NoteSummary]
    total: int
    limit: int
    offset: int


class NoteCreateRequest(_BaseModel):
    title: str = Field(..., min_length=1)
    style_theme: str = Field(default="clean", alias="styleTheme")
    layout_hints: Dict[str, Any] = Field(default_factory=dict, alias="layoutHints")
    blocks: List[BlockModel] = Field(default_factory=list)
    passport: Dict[str, Any] = Field(default_factory=dict)


class NoteUpdateRequest(_BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    style_theme: Optional[str] = Field(default=None, alias="styleTheme")
    layout_hints: Optional[Dict[str, Any]] = Field(default=None, alias="layoutHints")
    blocks: Optional[List[BlockModel]] = None
    passport: Optional[Dict[str, Any]] = None


__all__ = [
    "LinkPayload",
    "SourcePayload",
    "NoteSummary",
    "NoteDetail",
    "NoteListResponse",
    "NoteCreateRequest",
    "NoteUpdateRequest",
]
