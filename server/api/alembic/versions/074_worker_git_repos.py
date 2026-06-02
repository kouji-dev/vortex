"""workers: git_integrations owner/auth fields + git_repos table."""
from alembic import op
import sqlalchemy as sa

revision = "074_worker_git_repos"
down_revision = "073_catalog_usable_in_worker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- git_integrations: make org_id nullable (owner is org XOR user) ---
    op.alter_column("git_integrations", "org_id", nullable=True)

    # --- git_integrations: new owner/auth columns ---
    op.add_column(
        "git_integrations",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_git_integrations_user_id",
        "git_integrations",
        "users",
        ["user_id"],
        ["uuid"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_git_integrations_user_id",
        "git_integrations",
        ["user_id"],
    )
    op.add_column(
        "git_integrations",
        sa.Column("account_login", sa.String(255), nullable=True),
    )
    op.add_column(
        "git_integrations",
        sa.Column(
            "auth_type",
            sa.String(16),
            server_default="token",
            nullable=False,
        ),
    )

    # --- git_repos table ---
    op.create_table(
        "git_repos",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "integration_id",
            sa.UUID(),
            sa.ForeignKey("git_integrations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "default_branch",
            sa.String(255),
            nullable=False,
            server_default="main",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("git_repos")

    op.drop_index("ix_git_integrations_user_id", table_name="git_integrations")
    op.drop_constraint(
        "fk_git_integrations_user_id", "git_integrations", type_="foreignkey"
    )
    op.drop_column("git_integrations", "auth_type")
    op.drop_column("git_integrations", "account_login")
    op.drop_column("git_integrations", "user_id")

    op.alter_column("git_integrations", "org_id", nullable=False)
