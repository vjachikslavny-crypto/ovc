from __future__ import annotations

import datetime as dt
import uuid
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index
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
    # Hard deletion detaches metadata; API deletion is a tombstone. Never delete bytes.
    files = relationship("FileAsset", back_populates="note", passive_deletes="all")
    user = relationship("User", back_populates="notes")
    __table_args__ = (Index('ix_notes_owner_updated', 'user_id', 'updated_at'),)


class NoteChunk(Base):
    __tablename__ = "note_chunks"

    id = Column(String, primary_key=True, default=generate_uuid)
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True)
    idx = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)

    note = relationship("Note", back_populates="chunks")


class NoteLink(Base):
    __tablename__ = "note_links"

    id = Column(String, primary_key=True, default=generate_uuid)
    from_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True)
    to_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("from_id", "to_id", "reason", name="uq_note_links"),)

    source_note = relationship("Note", foreign_keys=[from_id], back_populates="links_from")
    target_note = relationship("Note", foreign_keys=[to_id], back_populates="links_to")


class NoteTag(Base):
    __tablename__ = "note_tags"

    id = Column(String, primary_key=True, default=generate_uuid)
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True)
    tag = Column(String, nullable=False, index=True)
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
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    relevance = Column(Float, default=1.0)

    note = relationship("Note", back_populates="sources")
    source = relationship("Source")


class MessageLog(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    role = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    user_id = Column(String, nullable=True, index=True)
    note_id = Column(String, nullable=True, index=True)
    mode = Column(String, nullable=True)
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


class UserGroupPreference(Base):
    __tablename__ = "user_group_preferences"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key = Column(String, primary_key=True)
    label = Column(String, nullable=False, default="Группа")
    color = Column(String, nullable=False, default="#8b5cf6")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)


class FileAsset(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True, default=generate_uuid)
    note_id = Column(String, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True)
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
    upload_op_id = Column(String, nullable=True, index=True)
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
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    note_id = Column(String, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True)
    payload_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="pending", index=True)
    tries = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)
    # Default 0 deliberately quarantines every historical row without rewriting it.
    protocol_version = Column(Integer, nullable=False, default=0, server_default="0")
    client_id = Column(String, nullable=True)
    remote_key = Column(String, nullable=True)
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    entity_remote_id = Column(String, nullable=True)
    base_revision = Column(Integer, nullable=True)
    dependency_json = Column(Text, nullable=False, default="[]", server_default="[]")
    wire_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    __table_args__ = (Index('ix_outbox_scope_due', 'user_id', 'client_id', 'remote_key', 'protocol_version', 'status', 'next_retry_at'),)


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
    user_id = Column(String, nullable=True)
    client_id = Column(String, nullable=True)
    remote_key = Column(String, nullable=True)
    op_id = Column(String, nullable=True)
    __table_args__ = (Index('ix_conflicts_scope_kind', 'user_id', 'client_id', 'remote_key', 'kind'),)


class SyncIdentity(Base):
    __tablename__ = "sync_identity"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class SyncAppliedOp(Base):
    __tablename__ = "sync_applied_ops"
    op_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    protocol_version = Column(Integer, nullable=False, default=0, server_default="0")
    client_id = Column(String, nullable=True)
    request_hash = Column(String, nullable=True)
    result_json = Column(Text, nullable=True)


class SyncChangeLog(Base):
    __tablename__ = "sync_change_log"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    op_type = Column(String, nullable=False)
    server_version = Column(Integer, nullable=False, default=0)
    deleted = Column(Boolean, nullable=False, default=False)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    protocol_version = Column(Integer, nullable=False, default=0, server_default="0")
    sequence = Column(Integer, nullable=True, unique=True)
    __table_args__ = (Index('ix_changes_owner_sequence', 'user_id', 'protocol_version', 'sequence'),)


class IntegrityArchive(Base):
    """Private, immutable repair evidence. Original IDs deliberately are not FKs."""
    __tablename__ = 'integrity_archive'
    id = Column(String, primary_key=True)
    repair_id = Column(String, nullable=False, index=True)
    source_table = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    category = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    original_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow)


class SyncPeerState(Base):
    __tablename__ = "sync_peer_state"
    user_id = Column(String, primary_key=True)
    client_id = Column(String, primary_key=True)
    remote_key = Column(String, primary_key=True)
    server_id = Column(String, nullable=True)
    remote_user_id = Column(String, nullable=True)
    cursor = Column(Integer, nullable=False, default=0)
    last_success_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    reachable = Column(Boolean, nullable=True)
    auth_required = Column(Boolean, nullable=False, default=False)


class SyncEntityMap(Base):
    __tablename__ = "sync_entity_map"
    user_id = Column(String, primary_key=True)
    client_id = Column(String, primary_key=True)
    remote_key = Column(String, primary_key=True)
    entity_type = Column(String, primary_key=True)
    local_id = Column(String, primary_key=True)
    remote_id = Column(String, nullable=False)
    remote_revision = Column(Integer, nullable=False, default=0)
    sha256 = Column(String, nullable=True)
    status = Column(String, nullable=False, default="mapped")
    __table_args__ = (UniqueConstraint("user_id", "client_id", "remote_key", "entity_type", "remote_id", name="uq_sync_entity_remote"),)
