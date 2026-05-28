"""gateway: prompt cache table.

Revision ID: 048_gateway_prompt_cache
Revises: 047_control_plane_gdpr
Create Date: 2026-05-28

Phase E1 of the Gateway plan. One table backs the no-Redis fallback cache:

- ``prompt_cache_entries``: composite primary key ``(org_id, cache_key)``;
  ``value`` is the cached LLMResponse dump as JSONB; ``expires_at`` is an
  absolute UTC timestamp set by the writer (``now() + ttl``). Lazy eviction
  on read deletes expired rows.

Org isolation is enforced via RLS — the same pattern used by every other
control-plane / gateway table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "049_gateway_prompt_cache"
down_revision = "048_gateway_catalog_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_cache_entries",
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cache_key", sa.String(128), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "org_id", "cache_key", name="pk_prompt_cache_entries"
        ),
    )
    op.create_index(
        "ix_prompt_cache_entries_expires_at",
        "prompt_cache_entries",
        ["expires_at"],
    )

    op.execute("ALTER TABLE prompt_cache_entries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE prompt_cache_entries FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY prompt_cache_entries_org_isolation ON prompt_cache_entries
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS prompt_cache_entries_org_isolation "
        "ON prompt_cache_entries"
    )
    op.drop_index(
        "ix_prompt_cache_entries_expires_at",
        table_name="prompt_cache_entries",
    )
    op.drop_table("prompt_cache_entries")
