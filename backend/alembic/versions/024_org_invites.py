"""Create org_invites table

Revision ID: 024_org_invites
Revises: 023_multitenancy
Create Date: 2026-04-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "024_org_invites"
down_revision = "023_multitenancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_invites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("invited_email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(64), unique=True, nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_org_invites_org_id", "org_invites", ["org_id"])
    op.create_index("ix_org_invites_token", "org_invites", ["token"])
    op.create_foreign_key("fk_org_invites_org_id", "org_invites", "orgs", ["org_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_org_invites_org_id", "org_invites", type_="foreignkey")
    op.drop_index("ix_org_invites_token", "org_invites")
    op.drop_index("ix_org_invites_org_id", "org_invites")
    op.drop_table("org_invites")
