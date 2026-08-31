"""
SQLAlchemy 2.0 declarative database models with pgvector support for Nyaya Legal Assistant.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Any

from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy models."""
    pass


class StatuteChunk(Base):
    """Stores structure-aware legal chunks extracted from BNS/BNSS bare acts."""

    __tablename__ = "statute_chunk"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    act: Mapped[str] = mapped_column(String(255), nullable=False)
    act_short: Mapped[str] = mapped_column(String(50), nullable=False)
    chapter: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    chapter_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    section_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    section_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subsection: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    clause: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    has_illustration: Mapped[bool] = mapped_column(Boolean, default=False)
    has_proviso: Mapped[bool] = mapped_column(Boolean, default=False)
    has_exception: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    references_json: Mapped[List[Any]] = mapped_column(JSONB, default=list)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768), nullable=True)


class OffenceClassification(Base):
    """First Schedule offence classification matrix rows (pages 158-189)."""

    __tablename__ = "offence_classification"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bns_section: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    offence_description: Mapped[str] = mapped_column(Text, nullable=False)
    punishment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cognizable: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bailable: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    triable_court: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768), nullable=True)


class StatutoryForm(Base):
    """Extracted statutory form metadata from Second Schedule (pages 190-249)."""

    __tablename__ = "statutory_form"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    form_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    enabling_section: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserDocument(Base):
    """Uploaded user documents (session-isolated)."""

    __tablename__ = "user_document"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="uploaded")
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[List["UserDocumentChunk"]] = relationship(
        "UserDocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class UserDocumentChunk(Base):
    """Chunked and embedded contents of user uploaded documents."""

    __tablename__ = "user_document_chunk"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_document.id", ondelete="CASCADE"), index=True, nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768), nullable=True)

    document: Mapped["UserDocument"] = relationship("UserDocument", back_populates="chunks")


class ChatSession(Base):
    """Anonymous or authenticated user chat sessions."""

    __tablename__ = "chat_session"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[List["ChatMessage"]] = relationship("ChatMessage", back_populates="session")


class ChatMessage(Base):
    """Chat message history with inline citations JSON."""

    __tablename__ = "chat_message"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("chat_session.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[List[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")


class Feedback(Base):
    """User feedback ratings on chat responses."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[str] = mapped_column(String(10), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
