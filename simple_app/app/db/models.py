from __future__ import annotations

import datetime as dt
import uuid
from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Note(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(Text, nullable=False)
    content_md = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    chunks = relationship("NoteChunk", back_populates="note", cascade="all, delete-orphan")
    tags = relationship("NoteTag", back_populates="note", cascade="all, delete-orphan")
    sources = relationship("NoteSource", back_populates="note", cascade="all, delete-orphan")


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
    reason = Column(String, nullable=False)
    confidence = Column(Float, nullable=False, default=0.5)

    __table_args__ = (UniqueConstraint("from_id", "to_id", "reason", name="uq_note_links"),)


class NoteTag(Base):
    __tablename__ = "note_tags"

    id = Column(String, primary_key=True, default=generate_uuid)
    note_id = Column(String, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    tag = Column(String, nullable=False)
    weight = Column(Float, default=1.0)

    note = relationship("Note", back_populates="tags")


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
