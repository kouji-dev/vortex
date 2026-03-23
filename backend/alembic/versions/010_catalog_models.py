"""Model catalog (DB + API metadata).

Revision ID: 010_catalog_models
Revises: 009_portal_api_keys
Create Date: 2026-03-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "010_catalog_models"
down_revision: str | None = "009_portal_api_keys"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("litellm_model_id", sa.String(length=255), nullable=False),
        sa.Column(
            "effort",
            sa.String(length=16),
            nullable=False,
            server_default="default",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "requires_entitlement",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("request_access_url", sa.String(length=512), nullable=True),
        sa.Column("catalog_metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "effort IN ('default', 'low', 'medium', 'high')",
            name="ck_catalog_models_effort",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_catalog_models_slug"),
    )
    op.create_index("ix_catalog_models_is_active", "catalog_models", ["is_active"])

    op.execute(
        sa.text(
            """
            INSERT INTO catalog_models (
                slug, display_name, description, litellm_model_id,
                effort, is_active, sort_order, requires_entitlement,
                request_access_url, catalog_metadata
            ) VALUES (
                'gpt-4o-mini',
                'GPT-4o mini',
                'Default fast chat model aligned with CHAT_MODEL default.',
                'gpt-4o-mini',
                'default',
                true,
                0,
                false,
                NULL,
                '{}'::jsonb
            )
            """
        )
    )
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


def downgrade() -> None:
    op.drop_index("ix_catalog_models_is_active", table_name="catalog_models")
    op.drop_table("catalog_models")
