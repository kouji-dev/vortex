"""control_plane: billing — subscriptions + invoices.

Revision ID: 044_control_plane_billing
Revises: ('042_control_plane_api_keys', '043_control_plane_idp_connections')
Create Date: 2026-05-28

Phase K of the Control Plane plan. Two tables:

- ``subscriptions``: one row per org/provider with current plan + status.
  ``customer_id`` is the provider-side identifier (e.g. Stripe ``cus_...``).
- ``invoices``: invoice history; ``pdf_url`` points at the BlobStore-hosted
  PDF (uploaded by the manual provider) or the Stripe-hosted invoice URL.

This revision merges the two open heads (api_keys + idp_connections).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "044_control_plane_billing"
down_revision = (
    "042_control_plane_api_keys",
    "043_control_plane_idp_connections",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscriptions ──────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
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
        # "stripe" | "manual" | future providers
        sa.Column("provider", sa.String(32), nullable=False),
        # Provider-side customer id (cus_xxx for Stripe; cus_manual_xxx for manual)
        sa.Column("customer_id", sa.String(128), nullable=False),
        # Provider-side subscription id (sub_xxx etc.)
        sa.Column("external_id", sa.String(128), nullable=True),
        # Plan shape:  "seat" | "usage" | "hybrid"
        sa.Column("plan_kind", sa.String(16), nullable=False),
        sa.Column("plan_code", sa.String(64), nullable=False),
        # Subscription status: trialing | active | past_due | canceled | incomplete
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="usd"),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="1"),
        # Per-line price metadata (mirrors :class:`Plan` for off-line audit).
        sa.Column("config_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "org_id", "provider",
            name="uq_subscriptions_org_provider",
        ),
    )
    op.create_index("ix_subscriptions_org_id", "subscriptions", ["org_id"])
    op.create_index(
        "ix_subscriptions_customer_id", "subscriptions", ["customer_id"],
    )
    op.create_index(
        "ix_subscriptions_external_id", "subscriptions", ["external_id"],
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )

    op.execute("ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY subscriptions_org_isolation ON subscriptions
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── invoices ───────────────────────────────────────────────────────
    op.create_table(
        "invoices",
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
        sa.Column(
            "subscription_id",
            UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Provider-side invoice id (in_xxx for Stripe).
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="usd"),
        # draft | open | paid | void | uncollectible
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        # BlobStore URL (manual provider) or hosted_invoice_url (Stripe).
        sa.Column("pdf_url", sa.String(2048), nullable=True),
        # Storage key inside BlobStore (e.g. ``invoices/{org_id}/{invoice_id}.pdf``).
        sa.Column("pdf_storage_key", sa.String(512), nullable=True),
        sa.Column("memo", sa.String(512), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "external_id", name="uq_invoices_external_id",
        ),
    )
    op.create_index("ix_invoices_org_id", "invoices", ["org_id"])
    op.create_index(
        "ix_invoices_subscription_id", "invoices", ["subscription_id"],
    )
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_due_at", "invoices", ["due_at"])

    op.execute("ALTER TABLE invoices ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invoices FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY invoices_org_isolation ON invoices
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS invoices_org_isolation ON invoices")
    op.drop_index("ix_invoices_due_at", table_name="invoices")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_subscription_id", table_name="invoices")
    op.drop_index("ix_invoices_org_id", table_name="invoices")
    op.drop_table("invoices")

    op.execute("DROP POLICY IF EXISTS subscriptions_org_isolation ON subscriptions")
    op.drop_index("ix_subscriptions_external_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_customer_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_org_id", table_name="subscriptions")
    op.drop_table("subscriptions")
