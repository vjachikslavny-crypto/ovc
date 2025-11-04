from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field, HttpUrl


class DraftActionBase(BaseModel):
    type: str


class CreateNoteAction(DraftActionBase):
    type: Literal["create_note"] = "create_note"
    title: str = Field(..., min_length=1)
    content_md: str = Field(..., min_length=1)


class UpdateNoteAction(DraftActionBase):
    type: Literal["update_note"] = "update_note"
    id: str
    patch_md: str = Field(..., min_length=1)
    position: Literal["append", "prepend"]


class AddLinkAction(DraftActionBase):
    type: Literal["add_link"] = "add_link"
    from_id: str
    to_title: str
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class AddTagAction(DraftActionBase):
    type: Literal["add_tag"] = "add_tag"
    note_id: str
    tag: str
    weight: Optional[float]


class SourcePayload(BaseModel):
    url: HttpUrl
    title: str
    domain: str
    published_at: Optional[str]
    summary: str


class AddSourceAction(DraftActionBase):
    type: Literal["add_source"] = "add_source"
    note_id: str
    source: SourcePayload


DraftAction = Union[
    CreateNoteAction,
    UpdateNoteAction,
    AddLinkAction,
    AddTagAction,
    AddSourceAction,
]


class AgentReply(BaseModel):
    reply: str
    draft: list[DraftAction]

