from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field, parse_obj_as

try:
    from pydantic import TypeAdapter
except ImportError:  # Pydantic v1
    TypeAdapter = None


class Annotations(BaseModel):
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    code: bool = False
    href: Optional[str] = None

    class Config:
        extra = "forbid"


class RichText(BaseModel):
    text: str
    annotations: Annotations = Field(default_factory=Annotations)

    class Config:
        extra = "forbid"


class HeadingData(BaseModel):
    level: int = Field(..., ge=1, le=3)
    text: str

    class Config:
        extra = "forbid"


class ParagraphData(BaseModel):
    parts: List[RichText]

    class Config:
        extra = "forbid"


class ListData(BaseModel):
    items: List[RichText]

    class Config:
        extra = "forbid"


class QuoteData(BaseModel):
    text: str
    cite: Optional[str] = None

    class Config:
        extra = "forbid"


class ImageData(BaseModel):
    src: str
    full: Optional[str] = None
    alt: Optional[str] = None
    w: Optional[int] = Field(default=None, ge=1)
    h: Optional[int] = Field(default=None, ge=1)

    class Config:
        extra = "forbid"


class AudioData(BaseModel):
    src: str
    duration: Optional[float] = Field(default=None, ge=0.0)
    waveform: Optional[str] = None

    class Config:
        extra = "forbid"


class VideoData(BaseModel):
    src: str
    poster: Optional[str] = None
    duration: Optional[float] = Field(default=None, ge=0.0)
    w: Optional[int] = Field(default=None, ge=1)
    h: Optional[int] = Field(default=None, ge=1)

    class Config:
        extra = "forbid"


class DocMeta(BaseModel):
    pages: Optional[int] = Field(default=None, ge=1)
    slides: Optional[int] = Field(default=None, ge=1)
    size: Optional[int] = Field(default=None, ge=0)

    class Config:
        extra = "forbid"


class DocData(BaseModel):
    kind: Literal["pdf", "docx", "rtf", "pptx", "txt"]
    src: str
    title: Optional[str] = None
    preview: Optional[str] = None
    meta: Optional[DocMeta] = None

    class Config:
        extra = "forbid"


class SheetData(BaseModel):
    kind: Literal["xlsx", "csv"]
    src: str
    sheets: List[str] = Field(default_factory=list)
    rows: Optional[int] = Field(default=None, ge=0)

    class Config:
        extra = "forbid"


class CodeData(BaseModel):
    language: Optional[str] = None
    src: str
    lines: Optional[int] = Field(default=None, ge=0)
    sha256: Optional[str] = None

    class Config:
        extra = "forbid"


class ArchiveEntry(BaseModel):
    path: str
    size: Optional[int] = Field(default=None, ge=0)

    class Config:
        extra = "forbid"


class ArchiveData(BaseModel):
    src: str
    tree: List[ArchiveEntry] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class LinkData(BaseModel):
    url: str
    title: Optional[str] = None
    desc: Optional[str] = None
    image: Optional[str] = None

    class Config:
        extra = "forbid"


class TableData(BaseModel):
    rows: List[List[str]]

    class Config:
        extra = "forbid"


class SourceData(BaseModel):
    url: str
    title: str
    domain: str
    published_at: Optional[str] = None
    summary: Optional[str] = None

    class Config:
        extra = "forbid"


class SummaryData(BaseModel):
    dateISO: str
    text: str

    class Config:
        extra = "forbid"


class TodoItem(BaseModel):
    id: Optional[str] = None
    text: str
    done: bool = False

    class Config:
        extra = "forbid"


class TodoData(BaseModel):
    items: List[TodoItem]

    class Config:
        extra = "forbid"


class DividerData(BaseModel):
    class Config:
        extra = "forbid"


class BlockBase(BaseModel):
    id: Optional[str] = None

    class Config:
        extra = "forbid"


class HeadingBlock(BlockBase):
    type: Literal["heading"]
    data: HeadingData


class ParagraphBlock(BlockBase):
    type: Literal["paragraph"]
    data: ParagraphData


class BulletListBlock(BlockBase):
    type: Literal["bulletList"]
    data: ListData


class NumberListBlock(BlockBase):
    type: Literal["numberList"]
    data: ListData


class QuoteBlock(BlockBase):
    type: Literal["quote"]
    data: QuoteData


class ImageBlock(BlockBase):
    type: Literal["image"]
    data: ImageData


class AudioBlock(BlockBase):
    type: Literal["audio"]
    data: AudioData


class VideoBlock(BlockBase):
    type: Literal["video"]
    data: VideoData


class DocBlock(BlockBase):
    type: Literal["doc"]
    data: DocData


class SheetBlock(BlockBase):
    type: Literal["sheet"]
    data: SheetData


class CodeBlock(BlockBase):
    type: Literal["code"]
    data: CodeData


class ArchiveBlock(BlockBase):
    type: Literal["archive"]
    data: ArchiveData


class LinkBlock(BlockBase):
    type: Literal["link"]
    data: LinkData


class TableBlock(BlockBase):
    type: Literal["table"]
    data: TableData


class SourceBlock(BlockBase):
    type: Literal["source"]
    data: SourceData


class SummaryBlock(BlockBase):
    type: Literal["summary"]
    data: SummaryData


class TodoBlock(BlockBase):
    type: Literal["todo"]
    data: TodoData


class DividerBlock(BlockBase):
    type: Literal["divider"]
    data: DividerData = Field(default_factory=DividerData)


BlockModel = Union[
    HeadingBlock,
    ParagraphBlock,
    BulletListBlock,
    NumberListBlock,
    QuoteBlock,
    ImageBlock,
    AudioBlock,
    VideoBlock,
    DocBlock,
    SheetBlock,
    CodeBlock,
    ArchiveBlock,
    LinkBlock,
    TableBlock,
    SourceBlock,
    SummaryBlock,
    TodoBlock,
    DividerBlock,
]


def dump_block(block: BlockModel) -> dict:
    """Return JSON-serializable dict for a typed block."""
    return block.dict(exclude_none=True)


def dump_blocks(blocks: List[BlockModel]) -> List[dict]:
    return [dump_block(block) for block in blocks]


def parse_blocks(raw_blocks: List[Any]) -> List[BlockModel]:
    """Parse a list of dictionaries into typed blocks."""
    if TypeAdapter is not None:  # Pydantic v2+
        adapter = TypeAdapter(List[BlockModel])
        return adapter.validate_python(raw_blocks)
    return parse_obj_as(List[BlockModel], raw_blocks)


__all__ = [
    "Annotations",
    "RichText",
    "BlockModel",
    "dump_block",
    "dump_blocks",
    "parse_blocks",
]
