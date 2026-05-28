"""control_plane: api_keys — minted per org, ``ap_`` prefix, sha256 hash storage.

Revision ID: 042_control_plane_api_keys
Revises: 041_control_plane_webhooks
Create Date: 2026-05-28

Phase C of the Control Plane plan. One table:

- ``api_keys``: org-scoped key rows. Plaintext (``ap_<base62>``) is never
  persisted; we store SHA-256 hex (``hash``), a recognition ``prefix``, and a
  flat ``scopes_json`` list of permission keys.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "042_control_plane_api_keys"
down_revision = "041_control_plane_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen alembic_version — control-plane revision ids exceed the default
    # 32-char limit. Idempotent (TYPE change is a no-op if already wider).
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("scopes_json", JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("hash", name="uq_api_keys_hash"),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["org_id"])
    op.create_index("ix_api_keys_actor_user_id", "api_keys", ["actor_user_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])

    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE api_keys FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY api_keys_org_isolation ON api_keys
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS api_keys_org_isolation ON api_keys")
    op.drop_index("ix_api_keys_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_actor_user_id", table_name="api_keys")
    op.drop_index("ix_api_keys_org_id", table_name="api_keys")
    op.drop_table("api_keys")
