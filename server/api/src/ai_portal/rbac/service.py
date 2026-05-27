"""RBAC service — role management + permission checks.

Backs ``require_permission`` in :mod:`ai_portal.control_plane.deps` and the
admin UI for assigning roles. Permission check semantics:

- Unknown ``perm`` → :class:`UnknownPermission` (caller has a typo)
- Actor with no role assignment in the org → deny
- Any matching ``role_permissions`` grant with a compatible ``resource_scope`` → allow

``resource_scope`` matching is dict-subset: grant ``{}`` (or ``NULL``) matches
any resource; grant ``{"kb_id": "x"}`` requires the caller to pass
``resource={"kb_id": "x"}`` (extra keys ignored).
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.rbac.catalog import permission_by_key
from ai_portal.rbac.model import (
    ActorRoleAssignment,
    Role,
    RolePermission,
)


ActorKind = Literal["user", "api_key", "service"]


@dataclass(frozen=True)
class Actor:
    """Caller of a permission check.

    Exactly one of ``user_id`` / ``api_key_id`` is set, mirroring the
    ``actor_role_assignments`` table shape.
    """

    org_id: _uuid.UUID
    kind: ActorKind = "user"
    user_id: int | None = None
    api_key_id: int | None = None


class UnknownPermission(Exception):
    """Raised when ``has_permission`` is called with a key not in the catalog."""


class RbacService:
    """RBAC orchestrator — assign roles, check permissions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── role lookup ──────────────────────────────────────────────────────────

    def get_system_role(self, name: str) -> Role | None:
        """Fetch a built-in system role by name (``owner`` / ``admin`` / ...)."""
        return self.db.scalars(
            select(Role).where(
                Role.name == name,
                Role.is_system.is_(True),
                Role.org_id.is_(None),
            )
        ).first()

    # ── assignments ──────────────────────────────────────────────────────────

    def assign_system_role(
        self,
        org_id: _uuid.UUID,
        *,
        role_name: str,
        user_id: int | None = None,
        api_key_id: int | None = None,
        resource_scope: dict | None = None,
    ) -> ActorRoleAssignment:
        """Assign a built-in system role to a user or api key."""
        if (user_id is None) == (api_key_id is None):
            raise ValueError("exactly one of user_id / api_key_id required")

        role = self.get_system_role(role_name)
        if role is None:
            raise ValueError(f"unknown system role: {role_name}")

        assignment = ActorRoleAssignment(
            org_id=org_id,
            role_id=role.id,
            actor_user_id=user_id,
            actor_api_key_id=api_key_id,
            resource_scope=resource_scope,
        )
        self.db.add(assignment)
        self.db.commit()
        self.db.refresh(assignment)
        return assignment

    def revoke_assignment(self, assignment_id: int) -> None:
        row = self.db.get(ActorRoleAssignment, assignment_id)
        if row is None:
            return
        self.db.delete(row)
        self.db.commit()

    # ── permission check ─────────────────────────────────────────────────────

    def has_permission(
        self,
        actor: Actor,
        perm: str,
        *,
        resource: dict | None = None,
    ) -> bool:
        """Return True iff *actor* holds *perm* in their org for *resource*.

        ``resource`` may be a dict like ``{"kb_id": "<uuid>"}``. Grants with
        empty / NULL ``resource_scope`` match any resource. Grants with a
        non-empty scope must be a dict-subset of the passed resource.
        """
        if permission_by_key(perm) is None:
            raise UnknownPermission(perm)

        # Find role_ids assigned to this actor in this org.
        q = select(ActorRoleAssignment.role_id, ActorRoleAssignment.resource_scope).where(
            ActorRoleAssignment.org_id == actor.org_id,
        )
        if actor.user_id is not None:
            q = q.where(ActorRoleAssignment.actor_user_id == actor.user_id)
        elif actor.api_key_id is not None:
            q = q.where(ActorRoleAssignment.actor_api_key_id == actor.api_key_id)
        else:
            return False

        rows = self.db.execute(q).all()
        if not rows:
            return False

        role_ids = [r[0] for r in rows]
        assignment_scopes = [r[1] for r in rows]

        # Pull permission grants for those roles matching perm.
        perm_rows = self.db.execute(
            select(RolePermission.role_id, RolePermission.resource_scope).where(
                RolePermission.role_id.in_(role_ids),
                RolePermission.permission_key == perm,
            )
        ).all()
        if not perm_rows:
            return False

        # Combined check: at least one grant whose (assignment_scope ∩ grant_scope)
        # is satisfied by the passed ``resource``.
        for grant_role_id, grant_scope in perm_rows:
            # Index of the corresponding assignment scope for this role.
            try:
                idx = role_ids.index(grant_role_id)
            except ValueError:
                continue
            asg_scope = assignment_scopes[idx]
            effective = _merge_scopes(asg_scope, grant_scope)
            if _scope_matches(effective, resource):
                return True

        return False


# ── helpers ───────────────────────────────────────────────────────────────────


def _merge_scopes(a: dict | None, b: dict | None) -> dict:
    """Combine two optional scope dicts. Keys from b override a on conflict."""
    out: dict = {}
    if a:
        out.update(a)
    if b:
        out.update(b)
    return out


def _scope_matches(scope: dict, resource: dict | None) -> bool:
    """True iff every key in *scope* equals the same key in *resource*."""
    if not scope:
        return True
    if not resource:
        return False
    for k, v in scope.items():
        if resource.get(k) != v:
            return False
    return True
