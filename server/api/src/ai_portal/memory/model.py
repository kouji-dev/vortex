"""Memory module models.

Original ``UserMemory`` (legacy single-row system profile) is kept intact for
backward compatibility with the chat memory injection path. The new pluggable
memory subsystem lives in the additional tables defined below.
"""
from __future__ import annotations

import enum
import uuid as _uuid
from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


# ── legacy UserMemory ────────────────────────────────────────────────────


class UserMemory(Base):
    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(16), default="manual", server_default="manual"
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── enums ────────────────────────────────────────────────────────────────


class ScopeKind(enum.Enum):
    user = "user"
    conversation = "conversation"
    assistant = "assistant"
    team = "team"
    org = "org"


class MemoryType(enum.Enum):
    fact = "fact"
    preference = "preference"
    entity = "entity"
    relation = "relation"
    episode = "episode"
    procedure = "procedure"


class ConflictStrategy(enum.Enum):
    newer_wins = "newer_wins"
    keep_both = "keep_both"
    prompt_user = "prompt_user"


# ── new tables ───────────────────────────────────────────────────────────


def _new_uuid() -> _uuid.UUID:
    return _uuid.uuid4()


class Memory(Base):
    """A single memory record (fact / preference / entity / relation / episode / procedure)."""

    __tablename__ = "memories"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_owner_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scope_kind: Mapped[ScopeKind] = mapped_column(
        Enum(ScopeKind, name="memory_scope_kind"), nullable=False
    )
    scope_ids_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, name="memory_type"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(4096), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    source_conversation_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    source_turn_ids_json: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    extractor_model: Mapped[str] = mapped_column(String(128), default="", server_default="")
    tags_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_memories_org_scope", "org_id", "scope_kind"),
        Index("ix_memories_org_type", "org_id", "type"),
        Index("ix_memories_deleted_at", "deleted_at"),
    )


class MemoryScope(Base):
    """Denormalised one-row-per-scope mapping for fast filter queries."""

    __tablename__ = "memory_scopes"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    memory_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_kind: Mapped[ScopeKind] = mapped_column(
        Enum(ScopeKind, name="memory_scope_kind"), nullable=False
    )
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class MemoryExtractionPolicy(Base):
    __tablename__ = "memory_extraction_policies"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_kind: Mapped[ScopeKind] = mapped_column(
        Enum(ScopeKind, name="memory_scope_kind"), nullable=False
    )
    triggers_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sensitive_block_json: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    model_allow_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    conflict_strategy: Mapped[ConflictStrategy] = mapped_column(
        Enum(ConflictStrategy, name="memory_conflict_strategy"),
        default=ConflictStrategy.newer_wins,
        server_default="newer_wins",
    )
    retention_days_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class MemoryRecallPolicy(Base):
    __tablename__ = "memory_recall_policies"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_kind: Mapped[ScopeKind] = mapped_column(
        Enum(ScopeKind, name="memory_scope_kind"), nullable=False
    )
    top_k: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    recency_weight: Mapped[float] = mapped_column(Float, default=0.2, server_default="0.2")
    importance_weight: Mapped[float] = mapped_column(
        Float, default=0.3, server_default="0.3"
    )
    filters_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class MemoryJob(Base):
    __tablename__ = "memory_jobs"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_kind: Mapped[ScopeKind] = mapped_column(
        Enum(ScopeKind, name="memory_scope_kind"), nullable=False
    )
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)


class MemoryUse(Base):
    __tablename__ = "memory_uses"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    memory_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_message_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MemoryPause(Base):
    __tablename__ = "memory_pauses"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    scope_kind: Mapped[ScopeKind | None] = mapped_column(
        Enum(ScopeKind, name="memory_scope_kind"), nullable=True
    )
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paused_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
