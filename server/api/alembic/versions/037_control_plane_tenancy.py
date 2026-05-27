"""control_plane: tenancy — extend orgs/users, add sessions/mfa/verifications/resets/members

Revision ID: 037_control_plane_tenancy
Revises: 036_threads_activity_index
Create Date: 2026-05-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "037_control_plane_tenancy"
down_revision = "036_threads_activity_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── orgs: add region + status ────────────────────────────────────────────
    op.add_column(
        "orgs",
        sa.Column(
            "region", sa.String(32), nullable=False, server_default="eu-west-1"
        ),
    )
    op.add_column(
        "orgs",
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="active"
        ),
    )

    # ── users: add name/locale/mfa_required/email_verified_at ────────────────
    op.add_column("users", sa.Column("name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("locale", sa.String(16), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "mfa_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    # ── user_sessions ────────────────────────────────────────────────────────
    op.create_table(
        "user_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_user_sessions_user_id",
        ),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index(
        "ix_user_sessions_user_id", "user_sessions", ["user_id"]
    )

    # ── user_mfa_factors ─────────────────────────────────────────────────────
    op.create_table(
        "user_mfa_factors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("secret", sa.String(255), nullable=False),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_user_mfa_factors_user_id",
        ),
    )
    op.create_index(
        "ix_user_mfa_factors_user_id", "user_mfa_factors", ["user_id"]
    )

    # ── email_verifications ──────────────────────────────────────────────────
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_email_verifications_user_id",
        ),
        sa.UniqueConstraint(
            "token_hash", name="uq_email_verifications_token_hash"
        ),
    )
    op.create_index(
        "ix_email_verifications_user_id", "email_verifications", ["user_id"]
    )

    # ── password_resets ──────────────────────────────────────────────────────
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_password_resets_user_id",
        ),
        sa.UniqueConstraint(
            "token_hash", name="uq_password_resets_token_hash"
        ),
    )
    op.create_index(
        "ix_password_resets_user_id", "password_resets", ["user_id"]
    )

    # ── org_members ──────────────────────────────────────────────────────────
    op.create_table(
        "org_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.String(16),
            nullable=False,
            server_default="member",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], ondelete="CASCADE",
            name="fk_org_members_org_id",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_org_members_user_id",
        ),
        sa.UniqueConstraint(
            "org_id", "user_id", name="uq_org_members_org_user"
        ),
    )
    op.create_index("ix_org_members_org_id", "org_members", ["org_id"])
    op.create_index("ix_org_members_user_id", "org_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_org_members_user_id", "org_members")
    op.drop_index("ix_org_members_org_id", "org_members")
    op.drop_table("org_members")

    op.drop_index("ix_password_resets_user_id", "password_resets")
    op.drop_table("password_resets")

    op.drop_index("ix_email_verifications_user_id", "email_verifications")
    op.drop_table("email_verifications")

    op.drop_index("ix_user_mfa_factors_user_id", "user_mfa_factors")
    op.drop_table("user_mfa_factors")

    op.drop_index("ix_user_sessions_user_id", "user_sessions")
    op.drop_table("user_sessions")

    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "mfa_required")
    op.drop_column("users", "locale")
    op.drop_column("users", "name")

    op.drop_column("orgs", "status")
    op.drop_column("orgs", "region")
