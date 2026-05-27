"""control_plane: rbac — permissions, roles, role_permissions, actor_role_assignments + seeds.

Revision ID: 039_control_plane_rbac
Revises: 038_control_plane_notify_core
Create Date: 2026-05-28

Phase B of the Control Plane plan. Adds the cross-module RBAC substrate:

- ``permissions``: mirror of the in-code ``ai_portal.rbac.catalog`` for joins
- ``roles``: built-in + org-custom roles
- ``role_permissions``: grants (with optional ``resource_scope``)
- ``actor_role_assignments``: bind users / api keys → role within org

Seeds the catalog and five system roles (``owner``, ``admin``, ``member``,
``viewer``, ``service``). The legacy ``rbac_policy`` table from
``029_enterprise_starter_tables`` stays — it powers per-org model / capability
/ tool allowlists and is orthogonal to this RBAC dimension.

Both tables under RLS via the existing ``app.current_org_id`` /
``app.is_rls_bypassed`` machinery from migration 028.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# ── Alembic identifiers ───────────────────────────────────────────────────────
revision = "039_control_plane_rbac"
down_revision = "038_control_plane_notify_core"
branch_labels = None
depends_on = None


# ── Catalog (kept in sync with src/ai_portal/rbac/catalog.py) ────────────────
# fmt: off
_PERMISSIONS: list[tuple[str, str, str]] = [
    # control_plane
    ("org:read", "Read org metadata", "control_plane"),
    ("org:update", "Update org metadata", "control_plane"),
    ("org:delete", "Delete / archive org", "control_plane"),
    ("members:read", "List org members", "control_plane"),
    ("members:invite", "Invite a new member", "control_plane"),
    ("members:remove", "Remove a member", "control_plane"),
    ("members:role:assign", "Assign roles to members", "control_plane"),
    ("api-keys:create", "Mint API keys", "control_plane"),
    ("api-keys:read", "List API keys (no secrets)", "control_plane"),
    ("api-keys:revoke", "Revoke API keys", "control_plane"),
    ("audit:read", "Search audit events", "control_plane"),
    ("audit:export", "Export audit events", "control_plane"),
    ("usage:read", "Read usage dashboard", "control_plane"),
    ("usage:export", "Export usage data", "control_plane"),
    ("budgets:read", "Read budgets + quotas", "control_plane"),
    ("budgets:write", "Create / update budgets + quotas", "control_plane"),
    ("webhooks:read", "List webhooks", "control_plane"),
    ("webhooks:write", "Create / update / delete webhooks", "control_plane"),
    ("settings:read", "Read org settings", "control_plane"),
    ("settings:write", "Update org settings + module flags", "control_plane"),
    ("rbac:read", "Read roles and permissions", "control_plane"),
    ("rbac:write", "Create / update roles", "control_plane"),
    ("idp:read", "Read SSO connections", "control_plane"),
    ("idp:write", "Configure SSO connections", "control_plane"),
    ("scim:read", "Read SCIM endpoints", "control_plane"),
    ("scim:write", "Configure SCIM endpoints", "control_plane"),
    ("billing:read", "Read billing + invoices", "control_plane"),
    ("billing:write", "Manage subscription + payment methods", "control_plane"),
    ("data:export", "Request GDPR data export", "control_plane"),
    ("data:delete", "Request GDPR data delete", "control_plane"),
    # gateway
    ("gateway:complete", "Call LLMs through gateway", "gateway"),
    ("gateway:embed", "Call embedding models", "gateway"),
    ("gateway:admin", "Manage routing / rate-limits / policies", "gateway"),
    ("gateway:traces:read", "View gateway traces", "gateway"),
    ("gateway:replay", "Replay historic gateway requests", "gateway"),
    # rag
    ("kb:create", "Create a knowledge base", "rag"),
    ("kb:read", "Read a knowledge base", "rag"),
    ("kb:write", "Ingest / update content in a KB", "rag"),
    ("kb:delete", "Delete a knowledge base", "rag"),
    ("kb:answer", "Run RAG answer queries", "rag"),
    ("kb:eval", "Run evaluation runs against a KB", "rag"),
    # memories
    ("memory:read", "Read user / org memories", "memories"),
    ("memory:write", "Write user / org memories", "memories"),
    ("memory:admin", "Administer memory store", "memories"),
    # workers
    ("workers:submit", "Submit worker tasks", "workers"),
    ("workers:approve", "Approve worker outputs", "workers"),
    ("workers:admin", "Manage worker fleet + queues", "workers"),
]
# fmt: on


# ── Built-in role definitions ────────────────────────────────────────────────
# owner -> all perms; admin -> all except billing:write + org:delete + rbac:write of role mgmt; etc.
def _role_perms() -> dict[str, list[str]]:
    all_keys = [k for k, _, _ in _PERMISSIONS]
    read_only = [k for k in all_keys if k.endswith(":read")]
    return {
        "owner": list(all_keys),
        "admin": [k for k in all_keys if k not in {"org:delete", "billing:write"}],
        "member": [
            "org:read",
            "members:read",
            "api-keys:read",
            "usage:read",
            "audit:read",
            "settings:read",
            "rbac:read",
            "idp:read",
            "scim:read",
            "billing:read",
            "budgets:read",
            "webhooks:read",
            "gateway:complete",
            "gateway:embed",
            "kb:create",
            "kb:read",
            "kb:write",
            "kb:answer",
            "memory:read",
            "memory:write",
            "workers:submit",
        ],
        "viewer": read_only,
        "service": [
            "gateway:complete",
            "gateway:embed",
            "kb:read",
            "kb:answer",
            "memory:read",
            "workers:submit",
        ],
    }


def upgrade() -> None:
    # ── permissions (catalog mirror) ─────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
    )
    op.create_index("ix_permissions_module", "permissions", ["module"])

    # ── roles ────────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "name", name="uq_roles_org_name"),
    )
    op.create_index("ix_roles_org_id", "roles", ["org_id"])

    # System roles (org_id NULL) are world-visible. Org-custom roles are RLS-scoped.
    op.execute("ALTER TABLE roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE roles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY roles_org_or_system ON roles
        USING (
            is_system = true
            OR org_id = app.current_org_id()
            OR app.is_rls_bypassed()
        )
        WITH CHECK (
            org_id = app.current_org_id() OR app.is_rls_bypassed()
        )
        """
    )

    # ── role_permissions ─────────────────────────────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "role_id",
            UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("permission_key", sa.String(64), nullable=False),
        sa.Column("resource_scope", JSONB, nullable=True),
        sa.UniqueConstraint(
            "role_id", "permission_key", name="uq_role_perm_role_key"
        ),
    )
    op.create_index("ix_role_perm_role_id", "role_permissions", ["role_id"])
    op.create_index(
        "ix_role_perm_permission_key", "role_permissions", ["permission_key"]
    )

    # ── actor_role_assignments ───────────────────────────────────────────────
    op.create_table(
        "actor_role_assignments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("actor_api_key_id", sa.Integer(), nullable=True),
        sa.Column("resource_scope", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(actor_user_id IS NOT NULL) <> (actor_api_key_id IS NOT NULL)",
            name="ck_actor_role_one_actor",
        ),
    )
    op.create_index("ix_ara_org_id", "actor_role_assignments", ["org_id"])
    op.create_index("ix_ara_role_id", "actor_role_assignments", ["role_id"])
    op.create_index(
        "ix_ara_user_id", "actor_role_assignments", ["actor_user_id"]
    )
    op.create_index(
        "ix_ara_api_key_id", "actor_role_assignments", ["actor_api_key_id"]
    )

    op.execute("ALTER TABLE actor_role_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE actor_role_assignments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY ara_org_isolation ON actor_role_assignments
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── seed: permissions catalog ────────────────────────────────────────────
    conn = op.get_bind()
    perm_rows = [
        {"key": k, "description": d, "module": m} for (k, d, m) in _PERMISSIONS
    ]
    if perm_rows:
        conn.execute(
            sa.text(
                "INSERT INTO permissions(key, description, module) "
                "VALUES (:key, :description, :module)"
            ),
            perm_rows,
        )

    # ── seed: built-in system roles + grants ─────────────────────────────────
    now = datetime.now(UTC)
    role_ids: dict[str, _uuid.UUID] = {}
    role_descriptions = {
        "owner": "Full access including billing + org deletion",
        "admin": "Manage members, settings, RBAC, modules — no billing or org deletion",
        "member": "Read-most + use modules (chat, kb, memory, workers)",
        "viewer": "Read-only access to data + dashboards",
        "service": "Machine identity — call gateway + read KB / memory",
    }
    for name in ("owner", "admin", "member", "viewer", "service"):
        rid = _uuid.uuid4()
        role_ids[name] = rid
        conn.execute(
            sa.text(
                "INSERT INTO roles(id, org_id, name, description, is_system, created_at) "
                "VALUES (:id, NULL, :name, :description, true, :created_at)"
            ),
            {
                "id": rid,
                "name": name,
                "description": role_descriptions[name],
                "created_at": now,
            },
        )

    grants = _role_perms()
    rp_rows = []
    for role_name, keys in grants.items():
        rid = role_ids[role_name]
        for k in keys:
            rp_rows.append({"role_id": rid, "permission_key": k})
    if rp_rows:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions(role_id, permission_key, resource_scope) "
                "VALUES (:role_id, :permission_key, NULL)"
            ),
            rp_rows,
        )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS ara_org_isolation ON actor_role_assignments"
    )
    op.drop_index("ix_ara_api_key_id", table_name="actor_role_assignments")
    op.drop_index("ix_ara_user_id", table_name="actor_role_assignments")
    op.drop_index("ix_ara_role_id", table_name="actor_role_assignments")
    op.drop_index("ix_ara_org_id", table_name="actor_role_assignments")
    op.drop_table("actor_role_assignments")

    op.drop_index("ix_role_perm_permission_key", table_name="role_permissions")
    op.drop_index("ix_role_perm_role_id", table_name="role_permissions")
    op.drop_table("role_permissions")

    op.execute("DROP POLICY IF EXISTS roles_org_or_system ON roles")
    op.drop_index("ix_roles_org_id", table_name="roles")
    op.drop_table("roles")

    op.drop_index("ix_permissions_module", table_name="permissions")
    op.drop_table("permissions")
