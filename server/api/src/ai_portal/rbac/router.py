"""Admin RBAC policy API — /api/admin/rbac/*"""

from __future__ import annotations

from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.core.db.rls import bypass_rls
from ai_portal.rbac.model import RbacPolicy
from ai_portal.rbac.schemas import RbacPolicyResponse, RbacPolicyUpdate

router = APIRouter(prefix="/api/admin/rbac", tags=["rbac"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, ("admin", "owner"))
    return user


@router.get("/policy", response_model=RbacPolicyResponse)
def get_policy(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> RbacPolicyResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    with bypass_rls(db):
        policy = db.scalars(
            select(RbacPolicy).where(RbacPolicy.org_id == user.org_id)
        ).first()

    if policy is None:
        # Return the implicit default — no DB row yet.
        return RbacPolicyResponse(
            id=0,
            org_id=user.org_id,
            model_allowlist=None,
            model_role_bindings={},
            capability_role_bindings={},
            tool_role_bindings={},
            default_policy="allow",
            updated_at=datetime.now(UTC),
        )

    return RbacPolicyResponse.model_validate(policy)


@router.put("/policy", response_model=RbacPolicyResponse)
def update_policy(
    body: RbacPolicyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> RbacPolicyResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    with bypass_rls(db):
        policy = db.scalars(
            select(RbacPolicy).where(RbacPolicy.org_id == user.org_id)
        ).first()

        if policy is None:
            policy = RbacPolicy(org_id=user.org_id)
            db.add(policy)

        policy.model_allowlist = body.model_allowlist
        policy.model_role_bindings = body.model_role_bindings
        policy.capability_role_bindings = body.capability_role_bindings
        policy.tool_role_bindings = body.tool_role_bindings
        policy.default_policy = body.default_policy
        policy.updated_at = datetime.now(UTC)
        policy.updated_by = user.id
        db.commit()
        db.refresh(policy)

    # Audit the change.
    try:
        from ai_portal.audit.service import log_event  # noqa: PLC0415
        log_event(
            org_id=user.org_id,
            actor_user_id=user.id,
            event_type="rbac.policy.updated",
            resource_type="policy",
            resource_id=str(policy.id),
            action="update",
            metadata={"default_policy": policy.default_policy},
        )
    except ImportError:
        pass

    return RbacPolicyResponse.model_validate(policy)
