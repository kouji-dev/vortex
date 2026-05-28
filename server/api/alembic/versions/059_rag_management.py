"""rag: management tables.

Phase A adds the enterprise RAG data model layered on top of the existing
``knowledge_bases`` table:

- ALTER ``knowledge_bases`` adds ``visibility``, ``embedder_id``,
  ``vector_backend``, ``chunker_id``, ``settings_json``, ``status``,
  ``slug``, ``tags``, ``default_retrieval_policy_id``, ``language``.
- ``kb_documents``         — document records (separate from legacy
  ``documents`` which remains untouched for back-compat).
- ``kb_document_versions`` — version history per document.
- ``kb_chunks``            — normalized chunk store with ACL + meta JSON.
- ``kb_acls``              — denormalized doc/chunk allow set.
- ``kb_chunk_embeddings``  — per-namespace pgvector store (default backend).

Revision ID: 059_rag_management
Revises: 058_workers_core
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "059_rag_management"
down_revision = "058_workers_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── knowledge_bases additive cols ─────────────────────────────────────
    op.add_column(
        "knowledge_bases",
        sa.Column("visibility", sa.String(16), nullable=False, server_default="private"),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("embedder_id", sa.String(128), nullable=False, server_default="voyage-3"),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("vector_backend", sa.String(32), nullable=False, server_default="pgvector"),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("chunker_id", sa.String(64), nullable=False, server_default="fixed_token"),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "settings_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("slug", sa.String(128), nullable=True),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "tags",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("default_retrieval_policy_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("language", sa.String(8), nullable=True),
    )
    op.create_index(
        "ix_knowledge_bases_status",
        "knowledge_bases",
        ["status"],
    )
    op.create_unique_constraint(
        "uq_knowledge_bases_org_slug",
        "knowledge_bases",
        ["org_id", "slug"],
    )

    # ── kb_documents ──────────────────────────────────────────────────────
    op.create_table(
        "kb_documents",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "kb_id",
            sa.Integer,
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_uri", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(512), nullable=False, server_default=""),
        sa.Column("mime", sa.String(128), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column(
            "source_acl_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "meta_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "latest_version_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("quarantine_reason", sa.Text, nullable=True),
        sa.Column("connector_id", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("kb_id", "source_uri", name="uq_kb_doc_uri"),
    )
    op.create_index("ix_kb_documents_kb_id", "kb_documents", ["kb_id"])
    op.create_index("ix_kb_documents_content_hash", "kb_documents", ["content_hash"])
    op.create_index("ix_kb_documents_status", "kb_documents", ["status"])

    # ── kb_document_versions ──────────────────────────────────────────────
    op.create_table(
        "kb_document_versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("kb_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("blob_ref", sa.String(1024), nullable=True),
        sa.Column(
            "meta_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("document_id", "version_no", name="uq_kb_doc_version"),
    )
    op.create_index(
        "ix_kb_document_versions_document_id",
        "kb_document_versions",
        ["document_id"],
    )

    # ── kb_chunks ─────────────────────────────────────────────────────────
    op.create_table(
        "kb_chunks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("kb_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kb_id",
            sa.Integer,
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("text", sa.Text, nullable=False, server_default=""),
        sa.Column("embedding_ref", sa.String(256), nullable=True),
        sa.Column(
            "acl_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "meta_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_kb_chunks_kb_id", "kb_chunks", ["kb_id"])
    op.create_index("ix_kb_chunks_document_id", "kb_chunks", ["document_id"])

    # ── kb_acls ───────────────────────────────────────────────────────────
    op.create_table(
        "kb_acls",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "kb_id",
            sa.Integer,
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_id", UUID(as_uuid=True), nullable=True),
        sa.Column("subject_kind", sa.String(16), nullable=False),  # user / group / public
        sa.Column("subject_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_kb_acls_kb_id", "kb_acls", ["kb_id"])
    op.create_index(
        "ix_kb_acls_kb_subject",
        "kb_acls",
        ["kb_id", "subject_kind", "subject_id"],
    )
    op.create_index("ix_kb_acls_document_id", "kb_acls", ["document_id"])
    op.create_index("ix_kb_acls_chunk_id", "kb_acls", ["chunk_id"])

    # ── kb_chunk_embeddings (default pgvector backend) ────────────────────
    # Per-namespace dim is honored at runtime by issuing one table per dim if
    # ever needed; for now use a wide pgvector(1536) column that fits common
    # embedder sizes. Resolver short-circuits dim on insert.
    op.execute(
        """
        CREATE TABLE kb_chunk_embeddings (
            chunk_id UUID PRIMARY KEY REFERENCES kb_chunks(id) ON DELETE CASCADE,
            kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            namespace VARCHAR(128) NOT NULL,
            dim INTEGER NOT NULL,
            embedding vector(1536),
            meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            acl_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.create_index(
        "ix_kb_chunk_embeddings_namespace",
        "kb_chunk_embeddings",
        ["namespace"],
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kb_chunk_embeddings")
    op.drop_index("ix_kb_acls_chunk_id", table_name="kb_acls")
    op.drop_index("ix_kb_acls_document_id", table_name="kb_acls")
    op.drop_index("ix_kb_acls_kb_subject", table_name="kb_acls")
    op.drop_index("ix_kb_acls_kb_id", table_name="kb_acls")
    op.drop_table("kb_acls")
    op.drop_index("ix_kb_chunks_document_id", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_kb_id", table_name="kb_chunks")
    op.drop_table("kb_chunks")
    op.drop_index(
        "ix_kb_document_versions_document_id",
        table_name="kb_document_versions",
    )
    op.drop_table("kb_document_versions")
    op.drop_index("ix_kb_documents_status", table_name="kb_documents")
    op.drop_index("ix_kb_documents_content_hash", table_name="kb_documents")
    op.drop_index("ix_kb_documents_kb_id", table_name="kb_documents")
    op.drop_table("kb_documents")
    op.drop_constraint(
        "uq_knowledge_bases_org_slug",
        "knowledge_bases",
        type_="unique",
    )
    op.drop_index("ix_knowledge_bases_status", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "language")
    op.drop_column("knowledge_bases", "default_retrieval_policy_id")
    op.drop_column("knowledge_bases", "tags")
    op.drop_column("knowledge_bases", "slug")
    op.drop_column("knowledge_bases", "status")
    op.drop_column("knowledge_bases", "settings_json")
    op.drop_column("knowledge_bases", "chunker_id")
    op.drop_column("knowledge_bases", "vector_backend")
    op.drop_column("knowledge_bases", "embedder_id")
    op.drop_column("knowledge_bases", "visibility")
