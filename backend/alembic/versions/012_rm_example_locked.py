"""Remove stub ``example-locked-premium`` catalog row.

Revision ID: 012_rm_example_locked
Revises: 011_catalog_model_config
Create Date: 2026-03-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012_rm_example_locked"
down_revision: str | None = "011_catalog_model_config"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("DELETE FROM catalog_models WHERE slug = 'example-locked-premium'")
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO catalog_models (
                slug, display_name, description, litellm_model_id,
                effort, is_active, sort_order, requires_entitlement,
                request_access_url, catalog_metadata
            ) VALUES (
                'example-locked-premium',
                'Premium (example)',
                'Example row: visible in catalog but not usable until entitled (stub).',
                'gpt-4o',
                'high',
                true,
                10,
                true,
                'https://example.com/request-model-access',
                '{"tier":"premium"}'::jsonb
            )
            """
        )
    )
