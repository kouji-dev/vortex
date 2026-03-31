"""Ensure catalog_models.api_model_id exists (repair partial / legacy DBs).

Revision ID: 016_catalog_api_model_id
Revises: 015_emb_1024
Create Date: 2026-03-30

Some databases ended up with ``catalog_models`` but without ``api_model_id``
(e.g. manual DDL or a failed migration). The ORM and ``010_catalog_models``
expect this column; add and backfill when missing.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_catalog_api_model_id"
down_revision: str | None = "015_emb_1024"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("catalog_models"):
        return
    col_names = {c["name"] for c in insp.get_columns("catalog_models")}
    if "api_model_id" in col_names:
        return

    op.add_column(
        "catalog_models",
        sa.Column("api_model_id", sa.String(length=255), nullable=True),
    )
    op.execute(
        sa.text("UPDATE catalog_models SET api_model_id = slug WHERE api_model_id IS NULL")
    )
    op.execute(
        sa.text(
            "UPDATE catalog_models SET api_model_id = 'gpt-4o-mini' "
            "WHERE api_model_id IS NULL OR btrim(api_model_id) = ''"
        )
    )
    op.alter_column(
        "catalog_models",
        "api_model_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )


def downgrade() -> None:
    # Column may have existed before this repair revision; do not drop.
    pass
