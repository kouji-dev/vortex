from __future__ import annotations

import enum
import uuid as _uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class KbVisibility(str, enum.Enum):
    private = "private"
    team = "team"
    org_public = "org_public"


class KbStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    deleted = "deleted"


class KbDocStatus(str, enum.Enum):
    pending = "pending"
    indexed = "indexed"
    quarantined = "quarantined"
    superseded = "superseded"
    deleted = "deleted"

CONNECTOR_KINDS: tuple[str, ...] = (
    "files",
    "github",
    "gitlab",
    "confluence",
    "s3",
)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── RAG management (Phase A) ────────────────────────────────────────
    visibility: Mapped[str] = mapped_column(
        String(16), default="private", server_default="private"
    )
    embedder_id: Mapped[str] = mapped_column(
        String(128), default="voyage-3", server_default="voyage-3"
    )
    vector_backend: Mapped[str] = mapped_column(
        String(32), default="pgvector", server_default="pgvector"
    )
    chunker_id: Mapped[str] = mapped_column(
        String(64), default="fixed_token", server_default="fixed_token"
    )
    settings_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tags: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    default_retrieval_policy_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_knowledge_bases_org_slug"),
    )


class ConversationKnowledgeBase(Base):
    """Which knowledge bases are attached to a chat thread (RAG scope)."""

    __tablename__ = "conversation_knowledge_bases"

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), primary_key=True
    )


class KnowledgeBaseConnector(Base):
    """Remote or logical source wired to a knowledge base (sync orchestration)."""

    __tablename__ = "knowledge_base_connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(255), default="")
    settings: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConnectorSyncJob(Base):
    """Queued / running sync work for a connector (extensible job orchestration)."""

    __tablename__ = "connector_sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    connector_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_base_connectors.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(32), default="full_sync")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    storage_path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    ingest_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunks_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunks_done: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)


# ── Phase A: enterprise RAG document/chunk/ACL tables ─────────────────────


class KbDocument(Base):
    """Enterprise document record (separate from legacy `documents`)."""

    __tablename__ = "kb_documents"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    source_uri: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(512), default="", server_default="")
    mime: Mapped[str] = mapped_column(String(128), default="", server_default="")
    content_hash: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_acl_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    meta_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending", index=True
    )
    latest_version_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    connector_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("kb_id", "source_uri", name="uq_kb_doc_uri"),
    )


class KbDocumentVersion(Base):
    __tablename__ = "kb_document_versions"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("kb_documents.id", ondelete="CASCADE"),
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    blob_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    meta_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_kb_doc_version"),
    )


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("kb_documents.id", ondelete="CASCADE"),
        index=True,
    )
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    text_: Mapped[str] = mapped_column(
        "text", Text, default="", server_default=""
    )
    embedding_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    acl_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    meta_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KbAcl(Base):
    """Denormalised per-document and per-chunk allow set."""

    __tablename__ = "kb_acls"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    chunk_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    subject_kind: Mapped[str] = mapped_column(String(16))  # user | group | public
    subject_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Phase M/N/P: eval framework + analytics + playground ─────────────────


class KbEval(Base):
    """Named test set scoped to a knowledge base.

    ``test_set_json`` shape:

    .. code-block:: json

        {"records": [
            {"id": "q1", "query": "...", "expected_doc_ids": ["d1","d2"],
             "expected_answer": "...", "judges": ["recall@5","mrr","faithfulness"]},
        ]}
    """

    __tablename__ = "kb_evals"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    test_set_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    judge_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    judge_temperature: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0.0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KbEvalRun(Base):
    """One execution of a KbEval against a snapshot of the KB."""

    __tablename__ = "kb_eval_runs"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    eval_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("kb_evals.id", ondelete="CASCADE"),
        index=True,
    )
    snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metrics_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    results_json: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    regression: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KbQuery(Base):
    """One retrieval/answer query against a KB (for analytics rollups)."""

    __tablename__ = "kb_queries"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text)
    hits_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    citations_json: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_cents: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KbFeedback(Base):
    """Per-citation thumbs up/down + optional comment."""

    __tablename__ = "kb_feedback"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    query_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    chunk_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[str] = mapped_column(String(8))  # up | down
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KbPlaygroundSession(Base):
    """Saved playground prompt + settings + retrieved chunks (deterministic replay)."""

    __tablename__ = "kb_playground_sessions"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    settings_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    retrieved_json: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
