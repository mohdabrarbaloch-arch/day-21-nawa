"""ORM models.

Audio is stored in the database on purpose. A generation is at most a few
megabytes, and keeping the bytes next to the row means the app is genuinely
portable: no shared volume, no object store, no filesystem that has to survive
a restart. Chunks are stored individually so regenerating one paragraph does
not mean re-synthesising the whole script.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GenerationStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    generations: Mapped[list[Generation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    pronunciations: Mapped[list[Pronunciation]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(140), default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalised_text: Mapped[str] = mapped_column(Text, default="", nullable=False)

    voice: Mapped[str] = mapped_column(String(80), nullable=False)
    voice_label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    rate: Mapped[float] = mapped_column(Float, default=1.0)
    pitch: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[float] = mapped_column(Float, default=1.0)

    status: Mapped[str] = mapped_column(String(20), default=GenerationStatus.QUEUED, index=True)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="generations")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="generation",
        cascade="all, delete-orphan",
        order_by="Chunk.index",
    )

    __table_args__ = (Index("ix_generations_user_created", "user_id", "created_at"),)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(
        ForeignKey("generations.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    audio: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Word timings are relative to this chunk; the API shifts them onto the
    # stitched timeline so the client never has to know about chunking.
    words: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    generation: Mapped[Generation] = relationship(back_populates="chunks")

    __table_args__ = (UniqueConstraint("generation_id", "index", name="uq_chunk_gen_index"),)


class Pronunciation(Base):
    """A per-user override: write this, say that."""

    __tablename__ = "pronunciations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    written: Mapped[str] = mapped_column(String(120), nullable=False)
    spoken: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="pronunciations")

    __table_args__ = (UniqueConstraint("user_id", "written", name="uq_pronunciation_user_written"),)
