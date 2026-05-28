"""memory: per-org envelope-encryption config.

Adds ``memory_encryption_configs``: one row per org, stores a Fernet DEK
wrapped by a deployment-managed KEK. Memories repository uses this row
to transparently encrypt/decrypt ``memories.text`` when ``enabled = true``.

All columns additive; ``memories`` table untouched (ciphertext is stored
in the same ``text`` column, prefixed with ``enc:v1:``).

Revision ID: 064_memory_encryption_config
Revises: 063_audit_usage_encryption_at_rest
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "064_memory_encryption_config"
down_revision = "063_audit_usage_encryption_at_rest"
branch_labels = None
depends_on = None


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_org_isolation ON {table}
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def upgrade() -> None:
    op.create_table(
        "memory_encryption_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "kek_ref", sa.String(128), nullable=False, server_default="env:MEMORY_KEK"
        ),
        sa.Column("wrapped_dek", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_memory_encryption_configs_org_id",
        "memory_encryption_configs",
        ["org_id"],
    )
    _enable_rls("memory_encryption_configs")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS memory_encryption_configs_org_isolation "
        "ON memory_encryption_configs"
    )
    op.drop_index(
        "ix_memory_encryption_configs_org_id",
        table_name="memory_encryption_configs",
    )
    op.drop_table("memory_encryption_configs")
