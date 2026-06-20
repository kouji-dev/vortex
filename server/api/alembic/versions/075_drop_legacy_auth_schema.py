"""drop legacy auth schema (scim, ldap, mfa, entra/scim user cols)"""
from alembic import op
import sqlalchemy as sa

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None

_TABLES = ["scim_group_members", "scim_groups", "scim_endpoints", "ldap_connections", "user_mfa_factors"]
_USER_COLS = ["entra_object_id", "scim_external_id", "mfa_required"]


def upgrade() -> None:
    op.execute("DELETE FROM idp_connections WHERE provider IN ('saml','okta','entra')")
    for t in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    for c in _USER_COLS:
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {c}")


def downgrade() -> None:
    # One-way cleanup; legacy tables are not recreated. Restore from 0xx if needed.
    raise NotImplementedError("legacy auth schema removal is not reversible")
