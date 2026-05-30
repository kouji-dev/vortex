"""control_plane: api_keys.rate_limits_json — per-key RPM / TPM / concurrency.

Additive JSONB column on ``api_keys``. NULL means "no per-key limit"; the
Gateway reads it to throttle. Shape: ``{"rpm": int, "tpm": int, "concurrency": int}``
(any subset of keys).

Revision ID: 071_control_plane_api_key_rate_limits
Revises: 070_control_plane_teams
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "071_control_plane_api_key_rate_limits"
down_revision = "070_control_plane_teams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("rate_limits_json", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "rate_limits_json")
