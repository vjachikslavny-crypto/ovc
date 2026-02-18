from __future__ import annotations

import datetime as dt
import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Note(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String, nullable=False)
    style_theme = Column(String, nullable=False, default="clean")
    layout_hints = Column(Text, nullable=False, default="{}")
    blocks_json = Column(Text, nullable=False, default="[]")
    passport_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)
    revision = Column(Integer, default=0, nullable=False)
    tombstone = Column(Boolean, default=False, nullable=False)
    client_origin = Column(String, nullable=True)
    last_client_ts = Column(DateTime, nullable=True)

    chunks = relationship("NoteChunk", back_populates="note", cascade="all, delete-orphan")
    tags = relationship("NoteTag", back_populates="note", cascade="all, delete-orphan")
    sources = relationship("NoteSource", back_populates="note", cascade="all, delete-orphan")
    links_from = relationship(
        "NoteLink",
        back_populates="source_note",
        foreign_keys="NoteLink.from_id",
        cascade="all, delete-orphan",
    )
    links_to = relationship(
        "NoteLink",
        back_populates="target_note",
        foreign_keys="NoteLink.to_id",
        cascade="all, delete-orphan",
    )
    files = relationship("FileAsset", back_populates="note", cascade="all, delete-orphan")
    user = relationship("User", back_populates="notes")


class NoteChunk(Base):
    __tablename__ = "note_chunks"

    id = Column(String, primary_key=True, default=generate_uuid)
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    idx = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)

    note = relationship("Note", back_populates="chunks")


class NoteLink(Base):
    __tablename__ = "note_links"

    id = Column(String, primary_key=True, default=generate_uuid)
    from_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    to_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    reason = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("from_id", "to_id", "reason", name="uq_note_links"),)

    source_note = relationship("Note", foreign_keys=[from_id], back_populates="links_from")
    target_note = relationship("Note", foreign_keys=[to_id], back_populates="links_to")


class NoteTag(Base):
    __tablename__ = "note_tags"

    id = Column(String, primary_key=True, default=generate_uuid)
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    tag = Column(String, nullable=False)
    weight = Column(Float, default=1.0)

    note = relationship("Note", back_populates="tags")

    __table_args__ = (UniqueConstraint("note_id", "tag", name="uq_note_tags"),)


class Source(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True, default=generate_uuid)
    url = Column(Text, nullable=False, unique=True)
    domain = Column(String, nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False, default="")
    published_at = Column(String)


class NoteSource(Base):
    __tablename__ = "note_sources"

    id = Column(String, primary_key=True, default=generate_uuid)
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    relevance = Column(Float, default=1.0)

    note = relationship("Note", back_populates="sources")
    source = relationship("Source")


class MessageLog(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    role = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class ActionLog(Base):
    __tablename__ = "action_log"

    id = Column(String, primary_key=True, default=generate_uuid)
    hash = Column(String, nullable=False, unique=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)


class GroupPreference(Base):
    __tablename__ = "group_preferences"

    key = Column(String, primary_key=True)
    label = Column(String, nullable=False, default="Группа")
    color = Column(String, nullable=False, default="#8b5cf6")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)


class FileAsset(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True, default=generate_uuid)
    note_id = Column(String, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    kind = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    path_original = Column(String, nullable=False)
    path_preview = Column(String, nullable=True)
    path_doc_html = Column(String, nullable=True)
    path_waveform = Column(String, nullable=True)
    path_slides_json = Column(String, nullable=True)
    path_slides_dir = Column(String, nullable=True)
    path_excel_summary = Column(String, nullable=True)
    path_excel_charts_json = Column(String, nullable=True)
    path_excel_charts_dir = Column(String, nullable=True)
    path_excel_chart_sheets_json = Column(String, nullable=True)  # OVC: excel - структурная информация о листах с диаграммами
    excel_charts_pages_keep = Column(Text, nullable=True)  # OVC: excel - JSON массив выбранных страниц пользователем
    excel_default_sheet = Column(String, nullable=True)
    path_video_original = Column(String, nullable=True)
    path_video_poster = Column(String, nullable=True)
    path_code_original = Column(String, nullable=True)
    path_markdown_raw = Column(String, nullable=True)
    hash_sha256 = Column(String, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    pages = Column(Integer, nullable=True)
    duration = Column(Float, nullable=True)
    words = Column(Integer, nullable=True)
    slides_count = Column(Integer, nullable=True)
    video_duration = Column(Float, nullable=True)
    video_width = Column(Integer, nullable=True)
    video_height = Column(Integer, nullable=True)
    video_mime = Column(String, nullable=True)
    code_language = Column(String, nullable=True)
    code_line_count = Column(Integer, nullable=True)
    markdown_line_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    note = relationship("Note", back_populates="files")
    user = relationship("User", back_populates="files")


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"

    id = Column(String, primary_key=True, default=generate_uuid)
    op_type = Column(String, nullable=False, index=True)
    note_id = Column(String, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True)
    payload_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="pending", index=True)
    tries = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)


class SyncNoteMap(Base):
    __tablename__ = "sync_note_map"

    local_note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    remote_note_id = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)


class SyncConflict(Base):
    __tablename__ = "sync_conflicts"

    id = Column(String, primary_key=True, default=generate_uuid)
    local_note_id = Column(String, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True)
    remote_note_id = Column(String, nullable=True, index=True)
    kind = Column(String, nullable=False, default="note_conflict")
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
