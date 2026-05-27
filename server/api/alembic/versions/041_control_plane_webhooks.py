"""control_plane: webhooks — outbound HTTP delivery + signing.

Revision ID: 041_control_plane_webhooks
Revises: 040_control_plane_audit_chain
Create Date: 2026-05-28

Phase F of the Control Plane plan. Adds three tables:

- ``webhooks``: registered outbound endpoint per org (URL + event-type filter).
- ``webhook_deliveries``: one row per send attempt; carries retry schedule
  (``next_attempt_at``) and last response for replay UX.
- ``webhook_event_types``: catalog of declared event types (seed: budgets,
  gateway, usage, orgs, api_keys). Modules upsert their own keys at startup.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "041_control_plane_webhooks"
down_revision = "040_control_plane_audit_chain"
branch_labels = None
depends_on = None


_SEED_EVENT_TYPES: list[tuple[str, str, str]] = [
    ("budget.exceeded", "Org budget hard limit reached; further calls blocked", "budgets"),
    ("budget.warning", "Org budget crossed a soft warning threshold (50/80/100%)", "budgets"),
    ("gateway.policy.violation", "Gateway policy denied a request", "gateway"),
    ("usage.threshold", "Configured usage threshold reached", "usage"),
    ("org.member.added", "A user was added to the org", "orgs"),
    ("org.member.removed", "A user was removed from the org", "orgs"),
    ("api_key.created", "A new API key was minted", "api_keys"),
    ("api_key.revoked", "An API key was revoked", "api_keys"),
]


def upgrade() -> None:
    # ── webhooks ────────────────────────────────────────────────────────────
    op.create_table(
        "webhooks",
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
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("event_types_json", JSONB, nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webhooks_org_id", "webhooks", ["org_id"])

    op.execute("ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webhooks FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY webhooks_org_isolation ON webhooks
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── webhook_deliveries ──────────────────────────────────────────────────
    op.create_table(
        "webhook_deliveries",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "webhook_id",
            UUID(as_uuid=True),
            sa.ForeignKey("webhooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload_json", JSONB, nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_response_status", sa.Integer(), nullable=True),
        sa.Column("last_response_body", sa.Text(), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"]
    )
    op.create_index(
        "ix_webhook_deliveries_org_id", "webhook_deliveries", ["org_id"]
    )
    op.create_index(
        "ix_webhook_deliveries_event_id", "webhook_deliveries", ["event_id"]
    )
    # Worker scan: cheap to find rows due for retry.
    op.create_index(
        "ix_webhook_deliveries_next_attempt_at",
        "webhook_deliveries",
        ["next_attempt_at"],
        postgresql_where=sa.text(
            "status IN ('pending', 'in_flight') AND next_attempt_at IS NOT NULL"
        ),
    )

    op.execute("ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webhook_deliveries FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY webhook_deliveries_org_isolation ON webhook_deliveries
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── webhook_event_types catalog ─────────────────────────────────────────
    op.create_table(
        "webhook_event_types",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True, autoincrement=True
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("key", name="uq_webhook_event_types_key"),
    )

    # Seed bundled control-plane event types.
    bind = op.get_bind()
    for key, desc, module in _SEED_EVENT_TYPES:
        bind.execute(
            sa.text(
                """
                INSERT INTO webhook_event_types (key, description, module)
                VALUES (:key, :desc, :module)
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"key": key, "desc": desc, "module": module},
        )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS webhook_deliveries_org_isolation ON webhook_deliveries"
    )
    op.execute("DROP POLICY IF EXISTS webhooks_org_isolation ON webhooks")

    op.drop_table("webhook_event_types")

    op.drop_index(
        "ix_webhook_deliveries_next_attempt_at", table_name="webhook_deliveries"
    )
    op.drop_index("ix_webhook_deliveries_event_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_org_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_webhook_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")

    op.drop_index("ix_webhooks_org_id", table_name="webhooks")
    op.drop_table("webhooks")
