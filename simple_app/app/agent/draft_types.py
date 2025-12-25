from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class DraftActionBase(BaseModel):
    type: str
    note_id: Optional[str] = Field(default=None, alias="noteId")

    class Config:
        allow_population_by_field_name = True


class BlockPayload(BaseModel):
    id: Optional[str] = None
    type: str
    data: dict[str, Any]


class InsertBlockAction(DraftActionBase):
    type: Literal["insert_block"] = "insert_block"
    after_id: Optional[str] = Field(None, alias="afterId")
    block: BlockPayload


class UpdateBlockAction(DraftActionBase):
    type: Literal["update_block"] = "update_block"
    block_id: str = Field(..., alias="id")
    patch: dict[str, Any]


class MoveBlockAction(DraftActionBase):
    type: Literal["move_block"] = "move_block"
    block_id: str = Field(..., alias="id")
    after_id: Optional[str] = Field(None, alias="afterId")


class AddTagAction(DraftActionBase):
    type: Literal["add_tag"] = "add_tag"
    tag: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RemoveTagAction(DraftActionBase):
    type: Literal["remove_tag"] = "remove_tag"
    tag: str


class AddLinkAction(DraftActionBase):
    type: Literal["add_link"] = "add_link"
    from_id: str = Field(..., alias="fromId")
    to_id: str = Field(..., alias="toId")
    reason: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SetStyleAction(DraftActionBase):
    type: Literal["set_style"] = "set_style"
    style_theme: str = Field(..., alias="styleTheme")
    layout_hints: Optional[dict[str, Any]] = Field(default=None, alias="layoutHints")


DraftAction = Union[
    InsertBlockAction,
    UpdateBlockAction,
    MoveBlockAction,
    AddTagAction,
    RemoveTagAction,
    AddLinkAction,
    SetStyleAction,
]


class AgentReply(BaseModel):
    reply: str
    draft: list[DraftAction]
