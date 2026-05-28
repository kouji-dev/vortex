"""Admin budgets + quotas API — /v1/budgets, /v1/quotas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.budgets.model import Budget, Quota
from ai_portal.budgets.schemas import (
    BudgetCreate,
    BudgetGraceExtend,
    BudgetOut,
    BudgetStatus,
    QuotaCreate,
    QuotaOut,
)
from ai_portal.budgets.service import _period_window, _spent_usd, extend_budget_grace, _effective_limit
from ai_portal.core.db.rls import bypass_rls, set_org_context

router = APIRouter(prefix="/v1", tags=["budgets"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, "admin", "owner")
    return user


# ── Quotas ──────────────────────────────────────────────────────────────────


@router.post("/quotas", response_model=QuotaOut, status_code=status.HTTP_201_CREATED)
def create_quota(
    body: QuotaCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> QuotaOut:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    with bypass_rls(db):
        set_org_context(db, user.org_id)
        q = Quota(
            org_id=user.org_id,
            name=body.name,
            scope_kind=body.scope_kind,
            scope_id=body.scope_id,
            unit=body.unit,
            period=body.period,
            max_qty=body.max_qty,
            action_on_breach=body.action_on_breach,
            created_by_user_id=user.id,
        )
        db.add(q)
        db.commit()
        db.refresh(q)
    return QuotaOut.model_validate(q)


@router.get("/quotas", response_model=list[QuotaOut])
def list_quotas(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> list[QuotaOut]:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    with bypass_rls(db):
        rows = db.scalars(select(Quota).where(Quota.org_id == user.org_id)).all()
    return [QuotaOut.model_validate(r) for r in rows]


@router.delete("/quotas/{quota_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quota(
    quota_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> None:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    with bypass_rls(db):
        q = db.get(Quota, quota_id)
        if q is None or q.org_id != user.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quota not found")
        db.delete(q)
        db.commit()


# ── Budgets ─────────────────────────────────────────────────────────────────


@router.post("/budgets", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(
    body: BudgetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> BudgetOut:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    with bypass_rls(db):
        set_org_context(db, user.org_id)
        b = Budget(
            org_id=user.org_id,
            name=body.name,
            scope_kind=body.scope_kind,
            scope_id=body.scope_id,
            limit_usd=body.limit_usd,
            period=body.period,
            period_start=body.period_start,
            period_end=body.period_end,
            warn_at_pcts=body.warn_at_pcts,
            hard_cutoff=body.hard_cutoff,
            webhook_on_threshold=body.webhook_on_threshold,
            created_by_user_id=user.id,
        )
        db.add(b)
        db.commit()
        db.refresh(b)
    return BudgetOut.model_validate(b)


@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> list[BudgetOut]:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    with bypass_rls(db):
        rows = db.scalars(select(Budget).where(Budget.org_id == user.org_id)).all()
    return [BudgetOut.model_validate(r) for r in rows]


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> None:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    with bypass_rls(db):
        b = db.get(Budget, budget_id)
        if b is None or b.org_id != user.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Budget not found")
        db.delete(b)
        db.commit()


@router.post("/budgets/{budget_id}/grace", response_model=BudgetOut)
def extend_grace(
    budget_id: int,
    body: BudgetGraceExtend,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> BudgetOut:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    with bypass_rls(db):
        b = db.get(Budget, budget_id)
        if b is None or b.org_id != user.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Budget not found")
        b = extend_budget_grace(
            db,
            budget_id=budget_id,
            grace_extension_usd=body.grace_extension_usd,
            grace_expires_at=body.grace_expires_at,
        )
        db.commit()
        db.refresh(b)
    return BudgetOut.model_validate(b)


@router.get("/budgets/{budget_id}/status", response_model=BudgetStatus)
def get_budget_status(
    budget_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> BudgetStatus:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    with bypass_rls(db):
        b = db.get(Budget, budget_id)
        if b is None or b.org_id != user.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Budget not found")
        now = datetime.now()
        start, end = _period_window(b.period, custom_start=b.period_start, custom_end=b.period_end)
        spent = _spent_usd(
            db, org_id=user.org_id, scope_kind=b.scope_kind, scope_id=b.scope_id,
            period_start=start, period_end=end,
        )
        eff_limit = _effective_limit(b, now)
        used_pct = float(spent / eff_limit * 100) if eff_limit > 0 else 0.0
        grace_active = bool(
            b.grace_extension_usd and b.grace_expires_at and now <= b.grace_expires_at
        )
    return BudgetStatus(
        budget_id=b.id,
        period_start=start,
        period_end=end,
        spent_usd=spent,
        limit_usd=b.limit_usd,
        effective_limit_usd=eff_limit,
        used_pct=used_pct,
        blocked=(b.hard_cutoff and spent >= eff_limit),
        grace_active=grace_active,
    )
