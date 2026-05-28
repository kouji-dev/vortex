"""gateway: playground + evals.

Phase I tables:

- ``playground_sessions``   — saved playground snapshots (one per user/org).
- ``model_evals``           — named test sets scoped to an org.
- ``model_eval_runs``       — one row per ``(eval, target_model)`` execution.

All three are org-scoped with the standard RLS policy mirroring the rest
of the gateway tables.

Revision ID: 055_gateway_playground_evals
Revises: 054_gateway_trace_request_json
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "055_gateway_playground_evals"
down_revision = "054_gateway_trace_request_json"
branch_labels = None
depends_on = None


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
    # ── playground_sessions ──────────────────────────────────────────────
    op.create_table(
        "playground_sessions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "snapshot_json",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_playground_sessions_org_id", "playground_sessions", ["org_id"])
    op.create_index(
        "ix_playground_sessions_user_id", "playground_sessions", ["user_id"]
    )
    _enable_rls("playground_sessions")

    # ── model_evals ──────────────────────────────────────────────────────
    op.create_table(
        "model_evals",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "test_set_json",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "name", name="uq_model_evals_org_name"),
    )
    op.create_index("ix_model_evals_org_id", "model_evals", ["org_id"])
    _enable_rls("model_evals")

    # ── model_eval_runs ──────────────────────────────────────────────────
    op.create_table(
        "model_eval_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "eval_id",
            UUID(as_uuid=True),
            sa.ForeignKey("model_evals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_model", sa.String(128), nullable=False),
        sa.Column(
            "results_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "summary_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_model_eval_runs_org_id", "model_eval_runs", ["org_id"])
    op.create_index("ix_model_eval_runs_eval_id", "model_eval_runs", ["eval_id"])
    op.create_index(
        "ix_model_eval_runs_eval_model_ran",
        "model_eval_runs",
        ["eval_id", "target_model", sa.text("ran_at DESC")],
    )
    _enable_rls("model_eval_runs")


def downgrade() -> None:
    _drop_rls("model_eval_runs")
    op.drop_index("ix_model_eval_runs_eval_model_ran", table_name="model_eval_runs")
    op.drop_index("ix_model_eval_runs_eval_id", table_name="model_eval_runs")
    op.drop_index("ix_model_eval_runs_org_id", table_name="model_eval_runs")
    op.drop_table("model_eval_runs")

    _drop_rls("model_evals")
    op.drop_index("ix_model_evals_org_id", table_name="model_evals")
    op.drop_table("model_evals")

    _drop_rls("playground_sessions")
    op.drop_index("ix_playground_sessions_user_id", table_name="playground_sessions")
    op.drop_index("ix_playground_sessions_org_id", table_name="playground_sessions")
    op.drop_table("playground_sessions")
