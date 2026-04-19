"""Enterprise starter tables: usage, audit, rbac_policy, usage_quota, retention.

Revision ID: 029_enterprise_starter_tables
Revises: 028_enterprise_rls_base
Create Date: 2026-04-19

All new tables carry ``org_id UUID NOT NULL`` and an RLS policy of
``org_id = app.current_org_id() OR app.is_rls_bypassed()``. Existing tables
are extended with columns only; RLS is not applied to them here.

- ``message_usage``: one row per assistant reply. Holds tokens / latency /
  cost. ``message_id`` FK uses ``ON DELETE SET NULL`` so usage survives
  retention sweeps of chat content.
- ``usage_rollup``: daily aggregation target for the RQ aggregator worker.
- ``audit_events``: append-only log. Immutability enforced by trigger —
  UPDATE/DELETE raise unless ``app.bypass_rls`` is on (sweeper role).
- ``rbac_policy``: one row per org. ``default_policy='allow'`` seeded on
  org creation keeps existing users unaffected.
- ``usage_quota``: per-org (optionally per-user, per-model) budgets.
- ``retention_policy``: per-org retention + legal hold.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

revision = "029_enterprise_starter_tables"
down_revision = "028_enterprise_rls_base"
branch_labels = None
depends_on = None


_RLS_TABLES = (
    "message_usage",
    "usage_rollup",
    "audit_events",
    "rbac_policy",
    "usage_quota",
    "retention_policy",
)


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


def upgrade() -> None:
    # ---- message_usage ------------------------------------------------------
    op.create_table(
        "message_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("chat_conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("api_model_id", sa.String(128), nullable=True),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_creation_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("tool_calls_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("capability_flags", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_message_usage_org_created", "message_usage", ["org_id", "created_at"])
    op.create_index("ix_message_usage_org_user_created", "message_usage", ["org_id", "user_id", "created_at"])
    op.create_index("ix_message_usage_org_model_created", "message_usage", ["org_id", "api_model_id", "created_at"])

    # ---- usage_rollup -------------------------------------------------------
    op.create_table(
        "usage_rollup",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("api_model_id", sa.String(128), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_grain", sa.String(16), nullable=False, server_default="day"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "user_id", "api_model_id", "period_start", "period_grain",
            name="uq_usage_rollup_bucket",
        ),
    )
    op.create_index("ix_usage_rollup_org_period", "usage_rollup", ["org_id", "period_start"])

    # ---- audit_events -------------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_type", sa.String(16), nullable=False, server_default="user"),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip_address", INET, nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_org_created", "audit_events", ["org_id", "created_at"])
    op.create_index("ix_audit_events_org_resource", "audit_events", ["org_id", "resource_type", "resource_id"])
    op.create_index("ix_audit_events_org_type_created", "audit_events", ["org_id", "event_type", "created_at"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.audit_events_block_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF app.is_rls_bypassed() THEN
                RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
            END IF;
            RAISE EXCEPTION 'audit_events is append-only (TG_OP=%)', TG_OP;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_no_update
        BEFORE UPDATE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION app.audit_events_block_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_no_delete
        BEFORE DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION app.audit_events_block_mutation();
        """
    )

    # ---- rbac_policy --------------------------------------------------------
    op.create_table(
        "rbac_policy",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("model_allowlist", JSONB, nullable=True),
        sa.Column("model_role_bindings", JSONB, nullable=False, server_default="{}"),
        sa.Column("capability_role_bindings", JSONB, nullable=False, server_default="{}"),
        sa.Column("tool_role_bindings", JSONB, nullable=False, server_default="{}"),
        sa.Column("default_policy", sa.String(8), nullable=False, server_default="allow"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # ---- usage_quota --------------------------------------------------------
    op.create_table(
        "usage_quota",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("api_model_id", sa.String(128), nullable=True),
        sa.Column("period", sa.String(8), nullable=False, server_default="month"),
        sa.Column("max_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("max_output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("action_on_breach", sa.String(16), nullable=False, server_default="block"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_quota_org_user_model", "usage_quota", ["org_id", "user_id", "api_model_id"])

    # ---- retention_policy ---------------------------------------------------
    op.create_table(
        "retention_policy",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("conversation_retention_days", sa.Integer(), nullable=True),
        sa.Column("audit_retention_days", sa.Integer(), nullable=False, server_default="2555"),
        sa.Column("usage_retention_days", sa.Integer(), nullable=False, server_default="2555"),
        sa.Column("upload_retention_days", sa.Integer(), nullable=True),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    for t in _RLS_TABLES:
        _enable_rls(t)

    # ---- Existing-table extensions -----------------------------------------
    op.add_column(
        "chat_messages",
        sa.Column("model_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column(
            "usage_id",
            sa.BigInteger(),
            sa.ForeignKey("message_usage.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "chat_uploads",
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "orgs",
        sa.Column(
            "deployment_mode",
            sa.String(16),
            nullable=False,
            server_default="selfhosted",
        ),
    )


def downgrade() -> None:
    op.drop_column("orgs", "deployment_mode")
    op.drop_column("chat_uploads", "legal_hold")
    op.drop_column("chat_messages", "usage_id")
    op.drop_column("chat_messages", "model_id")

    op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS app.audit_events_block_mutation()")

    for t in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {t}_org_isolation ON {t}")

    op.drop_table("retention_policy")
    op.drop_index("ix_usage_quota_org_user_model", table_name="usage_quota")
    op.drop_table("usage_quota")
    op.drop_table("rbac_policy")

    op.drop_index("ix_audit_events_org_type_created", table_name="audit_events")
    op.drop_index("ix_audit_events_org_resource", table_name="audit_events")
    op.drop_index("ix_audit_events_org_created", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_usage_rollup_org_period", table_name="usage_rollup")
    op.drop_table("usage_rollup")

    op.drop_index("ix_message_usage_org_model_created", table_name="message_usage")
    op.drop_index("ix_message_usage_org_user_created", table_name="message_usage")
    op.drop_index("ix_message_usage_org_created", table_name="message_usage")
    op.drop_table("message_usage")
