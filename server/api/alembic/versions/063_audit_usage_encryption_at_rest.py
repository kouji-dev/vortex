"""audit + usage: envelope-encrypted payload columns.

Adds nullable ``payload_enc`` / ``actor_enc`` columns to ``audit_events`` and
``meta_enc`` / ``pricing_snapshot_enc`` to ``usage_events``. Existing JSONB
columns stay so reads continue to work for historical rows that haven't been
re-encrypted yet.

Revision ID: 063_audit_usage_encryption_at_rest
Revises: 062_workers_approvals_mn
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "063_audit_usage_encryption_at_rest"
down_revision = "062_workers_approvals_mn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("payload_enc", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("actor_enc", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "usage_events",
        sa.Column("meta_enc", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "usage_events",
        sa.Column("pricing_snapshot_enc", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("usage_events", "pricing_snapshot_enc")
    op.drop_column("usage_events", "meta_enc")
    op.drop_column("audit_events", "actor_enc")
    op.drop_column("audit_events", "payload_enc")
