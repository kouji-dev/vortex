from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.auth.model import User as UserModel
from ai_portal.rbac.evaluator import evaluate as rbac_evaluate
from ai_portal.usage.service import check_quota


@dataclass(frozen=True, slots=True)
class GateResult:
    effective_model: str
    allowed_tools: list[str]
    allowed_capabilities: list[str]


async def evaluate(
    *,
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: int,
    requested_model: str,
    requested_tools: list[str],
    requested_capabilities: list[str],
) -> GateResult:
    # Sync quota check via run_sync
    def _quota_check(sync_session):
        return check_quota(sync_session, org_id=org_id, user_id=user_id, api_model_id=requested_model)

    decision = await session.run_sync(_quota_check)
    if decision.is_blocked:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "QUOTA_EXCEEDED", "message": decision.reason},
        )

    # Fetch the real user role from DB for RBAC checks
    def _get_role(sync_session):
        from sqlalchemy import select  # noqa: PLC0415
        user = sync_session.scalar(select(UserModel).where(UserModel.id == user_id))
        return user.role if user and user.role else "member"

    user_role = await session.run_sync(_get_role)

    class _UserProxy:
        role = user_role

    def _model_check(sync_session):
        return rbac_evaluate(sync_session, user=_UserProxy(), org_id=org_id,
                             resource_type="model", resource_key=requested_model)

    model_decision = await session.run_sync(_model_check)
    if not model_decision.allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "MODEL_FORBIDDEN", "message": model_decision.reason},
        )

    def _filter_tools(sync_session):
        allowed = []
        for t in requested_tools:
            d = rbac_evaluate(sync_session, user=_UserProxy(), org_id=org_id,
                              resource_type="tool", resource_key=t)
            if d.allowed:
                allowed.append(t)
        return allowed

    allowed_tools = await session.run_sync(_filter_tools)

    def _filter_caps(sync_session):
        allowed = []
        for c in requested_capabilities:
            d = rbac_evaluate(sync_session, user=_UserProxy(), org_id=org_id,
                              resource_type="capability", resource_key=c)
            if d.allowed:
                allowed.append(c)
        return allowed

    allowed_capabilities = await session.run_sync(_filter_caps)

    return GateResult(
        effective_model=requested_model,
        allowed_tools=allowed_tools,
        allowed_capabilities=allowed_capabilities,
    )
