"""gateway: catalog + credentials.

Revision ID: 048_gateway_catalog_credentials
Revises: 047_control_plane_gdpr
Create Date: 2026-05-28

Phase A3 + A4 of the Gateway plan. Two new tables:

- ``gateway_models`` (global, not org-scoped): provider model catalog with
  pricing + capabilities. Populated daily by ``catalog.sync.sync_models``.
- ``provider_credentials`` (org-scoped, RLS-protected): AES-GCM encrypted
  provider API keys. KEK from ``CONTROL_PLANE_KEK`` env.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "048_gateway_catalog_credentials"
down_revision = "047_control_plane_gdpr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── gateway_models (global) ─────────────────────────────────────────────
    op.create_table(
        "gateway_models",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "capabilities_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "price_input_per_1k_cents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "price_output_per_1k_cents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "price_cache_read_per_1k_cents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "provider", "model_id", name="uq_gateway_models_provider_model"
        ),
    )
    op.create_index("ix_gateway_models_provider", "gateway_models", ["provider"])

    # ── provider_credentials (org-scoped, RLS) ──────────────────────────────
    op.create_table(
        "provider_credentials",
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
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column(
            "label",
            sa.String(64),
            nullable=False,
            server_default="default",
        ),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "last_health_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "healthy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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
        sa.UniqueConstraint(
            "org_id",
            "provider",
            "label",
            name="uq_provider_credentials_org_provider_label",
        ),
    )
    op.create_index(
        "ix_provider_credentials_org_id", "provider_credentials", ["org_id"]
    )

    op.execute("ALTER TABLE provider_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE provider_credentials FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY provider_credentials_org_isolation ON provider_credentials
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS provider_credentials_org_isolation "
        "ON provider_credentials"
    )
    op.drop_index(
        "ix_provider_credentials_org_id", table_name="provider_credentials"
    )
    op.drop_table("provider_credentials")

    op.drop_index("ix_gateway_models_provider", table_name="gateway_models")
    op.drop_table("gateway_models")
