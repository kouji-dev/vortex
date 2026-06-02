"""catalog: usable_in_worker flag (gates the worker model picker)."""
from alembic import op
import sqlalchemy as sa

revision = "073_catalog_usable_in_worker"
down_revision = "072_control_plane_ldap_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_models",
        sa.Column(
            "usable_in_worker",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_catalog_models_usable_in_worker", "catalog_models", ["usable_in_worker"]
    )
    op.execute(
        "UPDATE catalog_models SET usable_in_worker = true "
        "WHERE api_model_id LIKE 'claude-%' OR api_model_id LIKE '%codex%'"
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_models_usable_in_worker", table_name="catalog_models")
    op.drop_column("catalog_models", "usable_in_worker")
