"""memory: pluggable memory subsystem tables.

Adds the new pluggable memory subsystem on top of the legacy ``user_memories``
table (kept untouched for backward compatibility):

- ``memories``                       — record itself, with pgvector embedding
- ``memory_scopes``                  — denormalised scope lookup
- ``memory_extraction_policies``     — per-org/scope extraction config
- ``memory_recall_policies``         — per-org/scope recall config
- ``memory_jobs``                    — background extract/compact/sweep queue
- ``memory_uses``                    — provenance: which memory used in which response
- ``memory_pauses``                  — per-user pause flag (global or per-scope)

Each new table is org-scoped and protected by the standard RLS isolation
policy that the rest of the platform uses.

Revision ID: 057_memory_pluggable
Revises: 056_rag_management
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "057_memory_pluggable"
down_revision = "056_rag_connectors"
branch_labels = None
depends_on = None


_SCOPE_KINDS = ("user", "conversation", "assistant", "team", "org")
_TYPES = ("fact", "preference", "entity", "relation", "episode", "procedure")
_CONFLICT = ("newer_wins", "keep_both", "prompt_user")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_org_isolation ON {table}
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def _drop_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    scope_kind = sa.Enum(*_SCOPE_KINDS, name="memory_scope_kind")
    mem_type = sa.Enum(*_TYPES, name="memory_type")
    conflict = sa.Enum(*_CONFLICT, name="memory_conflict_strategy")
    scope_kind.create(op.get_bind(), checkfirst=True)
    mem_type.create(op.get_bind(), checkfirst=True)
    conflict.create(op.get_bind(), checkfirst=True)

    # ── memories ─────────────────────────────────────────────────────────
    op.create_table(
        "memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_owner_json", JSONB, nullable=False),
        sa.Column(
            "scope_kind",
            sa.Enum(*_SCOPE_KINDS, name="memory_scope_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("scope_ids_json", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "type",
            sa.Enum(*_TYPES, name="memory_type", create_type=False),
            nullable=False,
        ),
        sa.Column("text", sa.String(4096), nullable=False),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("importance", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("source_conversation_id", sa.Integer, nullable=True),
        sa.Column(
            "source_turn_ids_json", JSONB, nullable=False, server_default="[]"
        ),
        sa.Column("extractor_model", sa.String(128), nullable=False, server_default=""),
        sa.Column("tags_json", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pinned", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Replace the ARRAY placeholder with a real pgvector column post-create
    # (alembic autogen plays nicely; do this with raw SQL to avoid the
    # pgvector type dependency in op.create_table).
    op.execute("ALTER TABLE memories DROP COLUMN embedding")
    op.execute("ALTER TABLE memories ADD COLUMN embedding vector(1536)")

    op.create_index("ix_memories_org_id", "memories", ["org_id"])
    op.create_index("ix_memories_source_conversation_id", "memories", ["source_conversation_id"])
    op.create_index("ix_memories_org_scope", "memories", ["org_id", "scope_kind"])
    op.create_index("ix_memories_org_type", "memories", ["org_id", "type"])
    op.create_index("ix_memories_deleted_at", "memories", ["deleted_at"])
    # HNSW vector index (cosine)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw "
        "ON memories USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    _enable_rls("memories")

    # ── memory_scopes ────────────────────────────────────────────────────
    op.create_table(
        "memory_scopes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scope_kind",
            sa.Enum(*_SCOPE_KINDS, name="memory_scope_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("scope_id", sa.String(64), nullable=False),
    )
    op.create_index("ix_memory_scopes_memory_id", "memory_scopes", ["memory_id"])
    op.create_index("ix_memory_scopes_scope_id", "memory_scopes", ["scope_id"])

    # ── memory_extraction_policies ──────────────────────────────────────
    op.create_table(
        "memory_extraction_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scope_kind",
            sa.Enum(*_SCOPE_KINDS, name="memory_scope_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("triggers_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("sensitive_block_json", JSONB, nullable=False, server_default="[]"),
        sa.Column("model_allow_json", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "conflict_strategy",
            sa.Enum(*_CONFLICT, name="memory_conflict_strategy", create_type=False),
            nullable=False,
            server_default="newer_wins",
        ),
        sa.Column("retention_days_json", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_memory_extraction_policies_org_id",
        "memory_extraction_policies",
        ["org_id"],
    )
    _enable_rls("memory_extraction_policies")

    # ── memory_recall_policies ──────────────────────────────────────────
    op.create_table(
        "memory_recall_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scope_kind",
            sa.Enum(*_SCOPE_KINDS, name="memory_scope_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("top_k", sa.Integer, nullable=False, server_default="8"),
        sa.Column("recency_weight", sa.Float, nullable=False, server_default="0.2"),
        sa.Column("importance_weight", sa.Float, nullable=False, server_default="0.3"),
        sa.Column("filters_json", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_memory_recall_policies_org_id", "memory_recall_policies", ["org_id"]
    )
    _enable_rls("memory_recall_policies")

    # ── memory_jobs ─────────────────────────────────────────────────────
    op.create_table(
        "memory_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "scope_kind",
            sa.Enum(*_SCOPE_KINDS, name="memory_scope_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("payload_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(2048), nullable=True),
    )
    op.create_index("ix_memory_jobs_org_id", "memory_jobs", ["org_id"])
    _enable_rls("memory_jobs")

    # ── memory_uses ─────────────────────────────────────────────────────
    op.create_table(
        "memory_uses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_text_hash", sa.String(64), nullable=False),
        sa.Column("response_message_id", sa.String(64), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_memory_uses_memory_id", "memory_uses", ["memory_id"])
    op.create_index(
        "ix_memory_uses_response_message_id", "memory_uses", ["response_message_id"]
    )

    # ── memory_pauses ───────────────────────────────────────────────────
    op.create_table(
        "memory_pauses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Integer, nullable=False),
        sa.Column(
            "scope_kind",
            sa.Enum(*_SCOPE_KINDS, name="memory_scope_kind", create_type=False),
            nullable=True,
        ),
        sa.Column("scope_id", sa.String(64), nullable=True),
        sa.Column(
            "paused_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_pauses_org_id", "memory_pauses", ["org_id"])
    op.create_index(
        "ix_memory_pauses_actor_user_id", "memory_pauses", ["actor_user_id"]
    )
    _enable_rls("memory_pauses")


def downgrade() -> None:
    for tbl in (
        "memory_pauses",
        "memory_uses",
        "memory_jobs",
        "memory_recall_policies",
        "memory_extraction_policies",
        "memory_scopes",
    ):
        _drop_rls(tbl)
        op.drop_table(tbl)
    _drop_rls("memories")
    op.execute("DROP INDEX IF EXISTS ix_memories_embedding_hnsw")
    op.drop_table("memories")

    sa.Enum(name="memory_conflict_strategy").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="memory_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="memory_scope_kind").drop(op.get_bind(), checkfirst=True)
