from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field, parse_obj_as

try:
    from pydantic import TypeAdapter, ConfigDict
except ImportError:  # Pydantic v1
    TypeAdapter = None
    ConfigDict = None


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


class BlockData(BaseModel):
    # Metadata emitted by the AI editor; retained through every save path.
    source: Optional[Literal["ai"]] = None


class HeadingData(BlockData):
    level: int = Field(..., ge=1, le=3)
    text: str

    class Config:
        extra = "forbid"


class ParagraphData(BlockData):
    parts: List[RichText]

    class Config:
        extra = "forbid"


class ListData(BlockData):
    items: List[RichText]

    class Config:
        extra = "forbid"


class QuoteData(BlockData):
    text: str
    cite: Optional[str] = None

    class Config:
        extra = "forbid"


class ImageData(BlockData):
    src: str
    full: Optional[str] = None
    alt: Optional[str] = None
    w: Optional[int] = Field(default=None, ge=1)
    h: Optional[int] = Field(default=None, ge=1)

    class Config:
        extra = "forbid"


class AudioData(BlockData):
    src: str
    mime: Optional[str] = None
    duration: Optional[float] = Field(default=None, ge=0.0)
    waveform: Optional[str] = None
    transcript: Optional[str] = None
    view: Literal["mini", "expanded"] = "mini"

    class Config:
        extra = "forbid"


class VideoData(BlockData):
    src: str
    title: Optional[str] = None
    poster: Optional[str] = None
    duration_sec: Optional[float] = Field(default=None, alias="durationSec", ge=0.0)
    width: Optional[int] = Field(default=None, ge=1)
    height: Optional[int] = Field(default=None, ge=1)
    mime: Optional[str] = None
    caption: Optional[str] = None
    view: Literal["inline", "cover", "compact"] = "inline"

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", populate_by_name=True)
    else:
        class Config:
            extra = "forbid"
            allow_population_by_field_name = True


class DocMeta(BaseModel):
    pages: Optional[int] = Field(default=None, ge=1)
    slides: Optional[int] = Field(default=None, ge=1)
    size: Optional[int] = Field(default=None, ge=0)
    words: Optional[int] = Field(default=None, ge=0)

    class Config:
        extra = "forbid"


class DocData(BlockData):
    kind: Literal["pdf", "doc", "docx", "rtf", "pptx", "txt"]
    src: str
    title: Optional[str] = None
    preview: Optional[str] = None
    meta: Optional[DocMeta] = None
    view: Literal["cover", "inline"] = "cover"  # OVC: pdf - режим просмотра

    class Config:
        extra = "forbid"


class SheetData(BlockData):
    kind: Literal["xlsx", "csv"]
    src: str
    sheets: List[str] = Field(default_factory=list)
    rows: Optional[int] = Field(default=None, ge=0)

    class Config:
        extra = "forbid"


class SlidesData(BlockData):
    kind: Literal["pptx"]
    src: str
    slides: Optional[str] = None  # OVC: pptx - опционально, если LibreOffice не установлен
    preview: Optional[str] = None
    count: Optional[int] = Field(default=None, ge=0)
    view: Literal["cover", "inline"] = "cover"

    class Config:
        extra = "forbid"


class CodeData(BlockData):
    src: str
    preview_url: Optional[str] = Field(default=None, alias="previewUrl")
    filename: str
    language: str
    size_bytes: Optional[int] = Field(default=None, alias="sizeBytes", ge=0)
    line_count: Optional[int] = Field(default=None, alias="lineCount", ge=0)
    view: Literal["inline", "cover", "compact"] = "inline"

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", populate_by_name=True)
    else:
        class Config:
            extra = "forbid"
            allow_population_by_field_name = True


class MarkdownData(BlockData):
    src: str
    preview_url: Optional[str] = Field(default=None, alias="previewUrl")
    filename: str
    size_bytes: Optional[int] = Field(default=None, alias="sizeBytes", ge=0)
    line_count: Optional[int] = Field(default=None, alias="lineCount", ge=0)
    view: Literal["inline", "cover", "compact"] = "inline"

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", populate_by_name=True)
    else:
        class Config:
            extra = "forbid"
            allow_population_by_field_name = True


class ArchiveEntry(BaseModel):
    path: str
    size: Optional[int] = Field(default=None, ge=0)

    class Config:
        extra = "forbid"


class ArchiveData(BlockData):
    src: str
    tree: List[ArchiveEntry] = Field(default_factory=list)

    class Config:
        extra = "forbid"


class LinkData(BlockData):
    url: str
    title: Optional[str] = None
    desc: Optional[str] = None
    image: Optional[str] = None

    class Config:
        extra = "forbid"


class TableData(BlockData):
    kind: Optional[Literal["xlsx", "xls", "csv"]] = None
    src: Optional[str] = None
    summary: Optional[str] = None
    view: Literal["cover", "inline"] = "cover"
    active_sheet: Optional[str] = Field(default=None, alias="activeSheet")
    charts: Optional[str] = None  # OVC: excel - URL к JSON с метаданными диаграмм
    rows: Optional[List[List[str]]] = None

    if ConfigDict is not None:  # Pydantic v2
        model_config = ConfigDict(extra="forbid", populate_by_name=True)
    else:  # Pydantic v1
        class Config:
            extra = "forbid"
            allow_population_by_field_name = True


class YouTubeData(BlockData):
    video_id: str = Field(alias="videoId")
    title: Optional[str] = None
    start_sec: Optional[float] = Field(default=None, alias="startSec", ge=0.0)
    view: Literal["inline", "cover", "compact"] = "inline"

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", populate_by_name=True)
    else:
        class Config:
            extra = "forbid"
            allow_population_by_field_name = True


class InstagramData(BlockData):
    url: str

    class Config:
        extra = "forbid"


class TikTokData(BlockData):
    url: str
    video_id: str = Field(alias="videoId")

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid", populate_by_name=True)
    else:
        class Config:
            extra = "forbid"
            allow_population_by_field_name = True


class SourceData(BlockData):
    url: str
    title: str
    domain: str
    published_at: Optional[str] = None
    summary: Optional[str] = None

    class Config:
        extra = "forbid"


class SummaryData(BlockData):
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


class TodoData(BlockData):
    items: List[TodoItem]

    class Config:
        extra = "forbid"


class DividerData(BlockData):
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


class SlidesBlock(BlockBase):
    type: Literal["slides"]
    data: SlidesData


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


class MarkdownBlock(BlockBase):
    type: Literal["markdown"]
    data: MarkdownData


class YouTubeBlock(BlockBase):
    type: Literal["youtube"]
    data: YouTubeData


class InstagramBlock(BlockBase):
    type: Literal["instagram"]
    data: InstagramData


class TikTokBlock(BlockBase):
    type: Literal["tiktok"]
    data: TikTokData


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
    SlidesBlock,
    SheetBlock,
    CodeBlock,
    ArchiveBlock,
    LinkBlock,
    TableBlock,
    MarkdownBlock,
    YouTubeBlock,
    InstagramBlock,
    TikTokBlock,
    SourceBlock,
    SummaryBlock,
    TodoBlock,
    DividerBlock,
]


def dump_block(block: BlockModel) -> dict:
    """Return JSON-serializable dict for a typed block."""
    # OVC: table - используем by_alias=True для правильной сериализации полей с alias
    return block.dict(exclude_none=True, by_alias=True)


def dump_blocks(blocks: List[BlockModel]) -> List[dict]:
    return [dump_block(block) for block in blocks]


def parse_blocks(raw_blocks: List[Any]) -> List[BlockModel]:
    """Parse a list of dictionaries into typed blocks."""
    if TypeAdapter is not None:  # Pydantic v2+
        adapter = TypeAdapter(List[BlockModel])
        return adapter.validate_python(raw_blocks)
    return parse_obj_as(List[BlockModel], raw_blocks)


def normalize_blocks(raw_blocks: List[Any]) -> List[dict]:
    """Canonical round trip, including AI provenance and legacy DOC kind.

    Reject unknown fields rather than silently deleting imported content. Callers
    reading historical data may retain the original JSON on validation failure.
    """
    return dump_blocks(parse_blocks(raw_blocks))


__all__ = [
    "Annotations",
    "RichText",
    "BlockModel",
    "dump_block",
    "dump_blocks",
    "parse_blocks",
]
