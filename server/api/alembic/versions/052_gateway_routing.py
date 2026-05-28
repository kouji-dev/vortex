"""gateway: routing policies + aliases.

Phase C of the Gateway plan. Two tables:

- ``routing_policies`` — per-org policy (strategy + rules_json).
- ``model_aliases`` — virtual model name that resolves to a policy.

Both are org-scoped with row-level security mirroring the rest of the
gateway tables.

Revision ID: 052_gateway_routing
Revises: 051_gateway_request_traces
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "052_gateway_routing"
down_revision = "051_gateway_request_traces"
branch_labels = None
depends_on = None


_STRATEGY_NAMES = (
    "static",
    "priority",
    "weighted",
    "cost_optimized",
    "latency_optimized",
    "capability_match",
    "custom_rules",
)


def upgrade() -> None:
    op.create_table(
        "routing_policies",
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
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column(
            "rules_json",
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
        sa.UniqueConstraint("org_id", "name", name="uq_routing_policies_org_name"),
        sa.CheckConstraint(
            f"strategy IN ({', '.join(repr(n) for n in _STRATEGY_NAMES)})",
            name="ck_routing_policies_strategy",
        ),
    )
    op.create_index(
        "ix_routing_policies_org_id", "routing_policies", ["org_id"]
    )

    op.execute("ALTER TABLE routing_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE routing_policies FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY routing_policies_org_isolation ON routing_policies
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    op.create_table(
        "model_aliases",
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
        sa.Column("alias", sa.String(128), nullable=False),
        sa.Column(
            "routing_policy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("routing_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "alias", name="uq_model_aliases_org_alias"),
    )
    op.create_index("ix_model_aliases_org_id", "model_aliases", ["org_id"])
    op.create_index(
        "ix_model_aliases_routing_policy_id",
        "model_aliases",
        ["routing_policy_id"],
    )

    op.execute("ALTER TABLE model_aliases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE model_aliases FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY model_aliases_org_isolation ON model_aliases
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS model_aliases_org_isolation ON model_aliases")
    op.drop_index("ix_model_aliases_routing_policy_id", table_name="model_aliases")
    op.drop_index("ix_model_aliases_org_id", table_name="model_aliases")
    op.drop_table("model_aliases")

    op.execute(
        "DROP POLICY IF EXISTS routing_policies_org_isolation ON routing_policies"
    )
    op.drop_index("ix_routing_policies_org_id", table_name="routing_policies")
    op.drop_table("routing_policies")
