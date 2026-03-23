"""Merge structured model config into catalog_metadata.

Revision ID: 011_catalog_model_config
Revises: 010_catalog_models
Create Date: 2026-03-22

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from ai_portal.catalog_specs import CATALOG_CONFIG_BACKFILL_BY_SLUG

revision: str = "011_catalog_model_config"
down_revision: str | None = "010_catalog_models"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    for slug, cfg in CATALOG_CONFIG_BACKFILL_BY_SLUG.items():
        patch = json.dumps({"config": cfg})
        conn.execute(
            sa.text(
                """
                UPDATE catalog_models
                SET catalog_metadata = COALESCE(catalog_metadata, '{}'::jsonb)
                    || CAST(:patch AS jsonb)
                WHERE slug = :slug
                """
            ),
            {"slug": slug, "patch": patch},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for slug in CATALOG_CONFIG_BACKFILL_BY_SLUG:
        conn.execute(
            sa.text(
                """
                UPDATE catalog_models
                SET catalog_metadata = COALESCE(catalog_metadata, '{}'::jsonb)
                    - 'config'
                WHERE slug = :slug
                """
            ),
            {"slug": slug},
        )
