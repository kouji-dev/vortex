"""SQLAlchemy ORM models for RBAC.

Two layers:

- Legacy ``RbacPolicy`` — per-org policy of allowlists + role bindings used by
  ``evaluator.py``. Kept for backwards compatibility with model/capability/tool
  guards already wired in chat + catalog.

- New control-plane RBAC (B-phase): a proper roles / role_permissions /
  actor_role_assignments model that backs ``RbacService.has_permission`` and
  the cross-module ``require_permission`` FastAPI dep.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


# ── Legacy per-org policy (used by evaluator.py) ──────────────────────────────


class RbacPolicy(Base):
    __tablename__ = "rbac_policy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    model_allowlist: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    model_role_bindings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    capability_role_bindings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tool_role_bindings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    default_policy: Mapped[str] = mapped_column(String(8), nullable=False, default="allow")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


# ── New control-plane RBAC tables ─────────────────────────────────────────────


class Role(Base):
    """A named bundle of permissions.

    System roles have ``is_system=True`` and ``org_id IS NULL`` — they are
    seeded by the migration and shared across all orgs. Org-custom roles
    carry an ``org_id`` and ``is_system=False``.
    """

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_roles_org_name"),
    )

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RolePermission(Base):
    """Permission grants on a role.

    ``permission_key`` is a free-form string drawn from
    :data:`ai_portal.rbac.catalog.PERMISSIONS`. We avoid a hard foreign key to a
    ``permissions`` table because the catalog lives in code; the ``permissions``
    seed table exists only for join queries from the admin UI.

    ``resource_scope`` is an optional JSON object that further restricts the
    grant (e.g. ``{"kb_id": "<uuid>"}``). Empty / NULL = unscoped.
    """

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "permission_key",
            name="uq_role_perm_role_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ActorRoleAssignment(Base):
    """Binds a user or api_key to a role within an org.

    Exactly one of ``actor_user_id`` or ``actor_api_key_id`` is non-null
    (CHECK constraint enforced at migration time).
    """

    __tablename__ = "actor_role_assignments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_api_key_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    resource_scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Permissions seed table ────────────────────────────────────────────────────


class PermissionRow(Base):
    """Mirror of :data:`ai_portal.rbac.catalog.PERMISSIONS` in the DB.

    Seeded + refreshed by the migration. The application never writes here at
    runtime — catalog.py is the source of truth.
    """

    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
