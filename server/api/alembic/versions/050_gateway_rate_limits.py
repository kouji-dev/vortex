"""gateway: rate limits — rate_limit_rules table.

Revision ID: 048_gateway_rate_limits
Revises: 047_control_plane_gdpr
Create Date: 2026-05-28

Phase D of the Gateway plan. One table:

- ``rate_limit_rules`` — per-org rule list. Each row binds a *dimension*
  (RPM / TPM / concurrent_requests) and a *period* (seconds) to a *scope*
  (org / key / user / team / model — encoded in ``scope_json``) plus a
  ``limit`` + ``burst`` value used by the token bucket.

Org-scoped with RLS, mirroring the rest of the control-plane.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "050_gateway_rate_limits"
down_revision = "049_gateway_prompt_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_rules",
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
            "scope_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("period_seconds", sa.Integer(), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("burst", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dimension IN ('rpm', 'tpm', 'concurrent_requests')",
            name="ck_rate_limit_rules_dimension",
        ),
        sa.CheckConstraint(
            "period_seconds > 0", name="ck_rate_limit_rules_period_positive"
        ),
        sa.CheckConstraint("limit_value >= 0", name="ck_rate_limit_rules_limit_nonneg"),
    )
    op.create_index("ix_rate_limit_rules_org_id", "rate_limit_rules", ["org_id"])
    op.create_index(
        "ix_rate_limit_rules_org_dim",
        "rate_limit_rules",
        ["org_id", "dimension"],
    )

    op.execute("ALTER TABLE rate_limit_rules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rate_limit_rules FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rate_limit_rules_org_isolation ON rate_limit_rules
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS rate_limit_rules_org_isolation ON rate_limit_rules"
    )
    op.drop_index("ix_rate_limit_rules_org_dim", table_name="rate_limit_rules")
    op.drop_index("ix_rate_limit_rules_org_id", table_name="rate_limit_rules")
    op.drop_table("rate_limit_rules")
