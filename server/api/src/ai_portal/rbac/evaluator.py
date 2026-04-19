"""RBAC policy evaluator.

Checks per-org policy rows to decide whether a user can access a resource.
Default policy is ``allow`` (backward-compatible: existing users see no change).

Resource types: ``model``, ``capability``, ``tool``.
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.model import User
from ai_portal.rbac.model import RbacPolicy

logger = logging.getLogger(__name__)

ResourceType = Literal["model", "capability", "tool"]


class Decision:
    def __init__(self, allowed: bool, reason: str = "") -> None:
        self.allowed = allowed
        self.reason = reason

    def __bool__(self) -> bool:
        return self.allowed


def evaluate(
    db: Session,
    *,
    user: User,
    org_id: uuid.UUID,
    resource_type: ResourceType,
    resource_key: str,
) -> Decision:
    """Evaluate whether *user* may access *resource_key* of *resource_type*.

    Loads the org's ``rbac_policy`` row (or returns ``allow`` if none exists —
    correct for orgs seeded before enterprise migration or with no policy row).
    """
    from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415

    with bypass_rls(db):
        policy = db.scalars(
            select(RbacPolicy).where(RbacPolicy.org_id == org_id)
        ).first()

    if policy is None:
        return Decision(allowed=True, reason="no policy — default allow")

    user_role = (user.role or "member").lower()

    # ── Model allowlist ───────────────────────────────────────────────────────
    if resource_type == "model":
        allowlist = policy.model_allowlist
        if allowlist is not None and resource_key not in allowlist:
            return Decision(allowed=False, reason=f"model {resource_key!r} not in allowlist")

        bindings: dict = policy.model_role_bindings or {}
        if resource_key in bindings:
            allowed_roles = [r.lower() for r in bindings[resource_key]]
            if user_role not in allowed_roles:
                return Decision(allowed=False, reason=f"role {user_role!r} not in model bindings for {resource_key!r}")

    # ── Capability bindings ───────────────────────────────────────────────────
    elif resource_type == "capability":
        bindings = policy.capability_role_bindings or {}
        if resource_key in bindings:
            allowed_roles = [r.lower() for r in bindings[resource_key]]
            if user_role not in allowed_roles:
                return Decision(allowed=False, reason=f"role {user_role!r} cannot use capability {resource_key!r}")

    # ── Tool bindings ─────────────────────────────────────────────────────────
    elif resource_type == "tool":
        bindings = policy.tool_role_bindings or {}
        if resource_key in bindings:
            allowed_roles = [r.lower() for r in bindings[resource_key]]
            if user_role not in allowed_roles:
                return Decision(allowed=False, reason=f"role {user_role!r} cannot use tool {resource_key!r}")

    # Fall through to default policy.
    if policy.default_policy == "deny":
        return Decision(allowed=False, reason="default_policy=deny")

    return Decision(allowed=True, reason="default allow")


def seed_default_policy(db: Session, org_id: uuid.UUID) -> None:
    """Ensure a permissive rbac_policy row exists for *org_id*.

    Called on org creation so admins can optionally tighten later.
    """
    from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415

    with bypass_rls(db):
        existing = db.scalars(
            select(RbacPolicy).where(RbacPolicy.org_id == org_id)
        ).first()
        if existing is None:
            db.add(RbacPolicy(org_id=org_id, default_policy="allow"))
            db.commit()
