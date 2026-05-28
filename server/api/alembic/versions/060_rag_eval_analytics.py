"""rag: eval framework + analytics + playground.

Adds:
- ``kb_evals``             — named test sets per KB (recall@k, MRR, nDCG, LLM-judge)
- ``kb_eval_runs``         — one execution recorded against a KB snapshot
- ``kb_queries``           — query log for analytics (top queries, zero-result)
- ``kb_feedback``          — thumbs up/down + comments per citation
- ``kb_playground_sessions`` — saved playground prompts/settings (deterministic replay)

Revision ID: 060_rag_eval_analytics
Revises: 059_rag_management
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "060_rag_eval_analytics"
down_revision = "059_rag_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── kb_evals ───────────────────────────────────────────────────────────
    op.create_table(
        "kb_evals",
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
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "test_set_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("judge_model", sa.String(128), nullable=True),
        sa.Column("judge_temperature", sa.Float, nullable=False, server_default="0.0"),
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
    )
    # `kb_id` column already has `index=True` → autogen creates `ix_kb_evals_kb_id`.

    # ── kb_eval_runs ───────────────────────────────────────────────────────
    op.create_table(
        "kb_eval_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "eval_id",
            UUID(as_uuid=True),
            sa.ForeignKey("kb_evals.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("snapshot_id", sa.String(128), nullable=True),
        sa.Column(
            "metrics_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "results_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("regression", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_kb_eval_runs_eval_id_ran_at", "kb_eval_runs", ["eval_id", "ran_at"])

    # ── kb_queries ─────────────────────────────────────────────────────────
    op.create_table(
        "kb_queries",
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
            index=True,
        ),
        sa.Column("user_id", sa.Integer, nullable=True, index=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("hits_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "citations_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Float, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_kb_queries_kb_created", "kb_queries", ["kb_id", "created_at"])

    # ── kb_feedback ────────────────────────────────────────────────────────
    op.create_table(
        "kb_feedback",
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
            index=True,
        ),
        sa.Column("query_id", UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("rating", sa.String(8), nullable=False),  # up | down
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # `kb_id` column already has `index=True` → autogen creates `ix_kb_feedback_kb_id`.

    # ── kb_playground_sessions ─────────────────────────────────────────────
    op.create_table(
        "kb_playground_sessions",
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
            index=True,
        ),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column(
            "settings_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "retrieved_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_kb_playground_kb_id", "kb_playground_sessions", ["kb_id"])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_playground_kb_id")
    op.drop_table("kb_playground_sessions")
    op.drop_table("kb_feedback")
    op.execute("DROP INDEX IF EXISTS ix_kb_queries_kb_created")
    op.drop_table("kb_queries")
    op.execute("DROP INDEX IF EXISTS ix_kb_eval_runs_eval_id_ran_at")
    op.drop_table("kb_eval_runs")
    op.drop_table("kb_evals")
