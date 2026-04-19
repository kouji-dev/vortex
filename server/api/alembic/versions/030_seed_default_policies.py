"""Seed default rbac_policy and retention_policy for orgs that were created before migration 029.

Revision ID: 030_seed_default_policies
Revises: 029_enterprise_starter_tables
Create Date: 2026-04-19

INSERT ... ON CONFLICT DO NOTHING so running twice is safe.
"""

from alembic import op

revision = "030_seed_default_policies"
down_revision = "029_enterprise_starter_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO rbac_policy (org_id, model_allowlist, model_role_bindings,
            capability_role_bindings, tool_role_bindings, default_policy, updated_at)
        SELECT id, NULL, '{}', '{}', '{}', 'allow', now()
        FROM orgs
        ON CONFLICT (org_id) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO retention_policy (org_id, conversation_retention_days,
            audit_retention_days, usage_retention_days, upload_retention_days,
            legal_hold, updated_at)
        SELECT id, NULL, 2555, 2555, NULL, FALSE, now()
        FROM orgs
        ON CONFLICT (org_id) DO NOTHING
        """
    )


def downgrade() -> None:
    pass
