"""Add users.entra_object_id (partial unique).

Revision ID: 005_entra_oid
Revises: 004_rag
Create Date: 2026-03-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_entra_oid"
down_revision: Union[str, None] = "004_rag"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("entra_object_id", sa.String(length=36), nullable=True))
    op.create_index(
        "uq_users_entra_object_id",
        "users",
        ["entra_object_id"],
        unique=True,
        postgresql_where=sa.text("entra_object_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_entra_object_id", table_name="users")
    op.drop_column("users", "entra_object_id")
