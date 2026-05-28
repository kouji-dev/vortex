"""gateway: guardrails.

Phase F of the Gateway plan. Two tables:

- ``guardrail_policies`` — per-org named bundle of guardrails + actions.
- ``guardrail_violations`` — append-only log of non-allow verdicts.

Both are org-scoped with row-level security mirroring the rest of the
gateway tables.

Revision ID: 053_gateway_guardrails
Revises: 052_gateway_routing
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "053_gateway_guardrails"
down_revision = "052_gateway_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── guardrail_policies ───────────────────────────────────────────────
    op.create_table(
        "guardrail_policies",
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
            "bundle_json",
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
        sa.UniqueConstraint(
            "org_id", "name", name="uq_guardrail_policies_org_name"
        ),
    )
    op.create_index(
        "ix_guardrail_policies_org_id", "guardrail_policies", ["org_id"]
    )
    op.execute("ALTER TABLE guardrail_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE guardrail_policies FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY guardrail_policies_org_isolation ON guardrail_policies
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── guardrail_violations ─────────────────────────────────────────────
    op.create_table(
        "guardrail_violations",
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
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("guardrail", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column(
            "evidence_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "verdict IN ('redact', 'block', 'flag')",
            name="ck_guardrail_violations_verdict",
        ),
    )
    op.create_index(
        "ix_guardrail_violations_org_ts",
        "guardrail_violations",
        ["org_id", sa.text("ts DESC")],
    )
    op.create_index(
        "ix_guardrail_violations_request_id",
        "guardrail_violations",
        ["request_id"],
    )
    op.execute("ALTER TABLE guardrail_violations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE guardrail_violations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY guardrail_violations_org_isolation ON guardrail_violations
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS guardrail_violations_org_isolation "
        "ON guardrail_violations"
    )
    op.drop_index(
        "ix_guardrail_violations_request_id", table_name="guardrail_violations"
    )
    op.drop_index(
        "ix_guardrail_violations_org_ts", table_name="guardrail_violations"
    )
    op.drop_table("guardrail_violations")

    op.execute(
        "DROP POLICY IF EXISTS guardrail_policies_org_isolation "
        "ON guardrail_policies"
    )
    op.drop_index(
        "ix_guardrail_policies_org_id", table_name="guardrail_policies"
    )
    op.drop_table("guardrail_policies")
