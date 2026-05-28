"""Budgets + quotas service.

- ``check_quota`` — hard cap per unit per period scoped to org/user/key/team.
- ``check_budget`` — USD-denominated budget with soft warns + hard cutoff +
  grace-period extension. Fires webhook on 50/80/100 % thresholds.

Both checks are *projections*: they compute current consumption from
``usage_events`` and tell the caller whether the next emit would breach the
limit. The caller is expected to call ``check_*`` BEFORE the action and then
``emit_usage`` after success.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.budgets.model import Budget, BudgetAlert, Quota
from ai_portal.core.db.rls import bypass_rls
from ai_portal.usage.events_model import UsageEvent


# ── Period helpers ──────────────────────────────────────────────────────────


def _period_window(
    period: str,
    *,
    now: datetime | None = None,
    custom_start: datetime | None = None,
    custom_end: datetime | None = None,
) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    if period == "custom":
        if not custom_start or not custom_end:
            raise ValueError("custom period requires period_start + period_end")
        return custom_start, custom_end
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year = start.year + (start.month // 12)
        month = (start.month % 12) + 1
        return start, start.replace(year=year, month=month, day=1)
    raise ValueError(f"unknown period: {period}")


# ── Decision objects ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    action: str  # allow | warn | block
    reason: str = ""
    current_qty: Decimal = Decimal("0")
    max_qty: Decimal | None = None

    @property
    def is_blocked(self) -> bool:
        return self.action == "block"


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    action: str  # allow | warn | block
    spent_usd: Decimal
    effective_limit_usd: Decimal
    used_pct: float
    fired_thresholds: tuple[int, ...] = ()
    reason: str = ""

    @property
    def is_blocked(self) -> bool:
        return self.action == "block"


# ── Quota check ─────────────────────────────────────────────────────────────


def _matches_scope(scope_kind: str, scope_id: str | None, *, user_id: int | None, api_key_id: int | None, team_id: int | None) -> bool:
    if scope_kind == "org":
        return scope_id is None
    if scope_kind == "user":
        return scope_id is not None and user_id is not None and str(user_id) == scope_id
    if scope_kind == "api_key":
        return scope_id is not None and api_key_id is not None and str(api_key_id) == scope_id
    if scope_kind == "team":
        return scope_id is not None and team_id is not None and str(team_id) == scope_id
    return False


def check_quota(
    db: Session,
    *,
    org_id: _uuid.UUID,
    unit: str,
    incoming_qty: Decimal,
    user_id: int | None = None,
    api_key_id: int | None = None,
    team_id: int | None = None,
    now: datetime | None = None,
) -> QuotaDecision:
    """Check every quota matching the (unit, scope) tuple. Most-restrictive wins."""
    with bypass_rls(db):
        quotas = db.scalars(
            select(Quota).where(
                Quota.org_id == org_id,
                Quota.unit == unit,
                Quota.disabled_at.is_(None),
            )
        ).all()

    if not quotas:
        return QuotaDecision("allow")

    decision = QuotaDecision("allow")
    for q in quotas:
        if not _matches_scope(q.scope_kind, q.scope_id, user_id=user_id, api_key_id=api_key_id, team_id=team_id):
            continue
        start, end = _period_window(q.period, now=now)
        with bypass_rls(db):
            current: Decimal = db.scalar(
                select(func.coalesce(func.sum(UsageEvent.qty), Decimal("0"))).where(
                    UsageEvent.org_id == org_id,
                    UsageEvent.unit == unit,
                    UsageEvent.ts >= start,
                    UsageEvent.ts < end,
                )
            ) or Decimal("0")
        projected = current + Decimal(incoming_qty)
        if projected > q.max_qty:
            return QuotaDecision(
                action=q.action_on_breach,
                reason=f"quota '{q.name}' exceeded: {projected} > {q.max_qty} {unit}",
                current_qty=current,
                max_qty=q.max_qty,
            )
    return decision


# ── Budget check + alert firing ─────────────────────────────────────────────


def _spent_usd(
    db: Session, *, org_id: _uuid.UUID, scope_kind: str, scope_id: str | None,
    period_start: datetime, period_end: datetime,
) -> Decimal:
    q = select(func.coalesce(func.sum(UsageEvent.cost_usd), Decimal("0"))).where(
        UsageEvent.org_id == org_id,
        UsageEvent.ts >= period_start,
        UsageEvent.ts < period_end,
    )
    if scope_kind == "user" and scope_id is not None:
        q = q.where(UsageEvent.actor_user_id == int(scope_id))
    elif scope_kind == "api_key" and scope_id is not None:
        q = q.where(UsageEvent.actor_api_key_id == int(scope_id))
    elif scope_kind == "team" and scope_id is not None:
        q = q.where(UsageEvent.actor_team_id == int(scope_id))
    with bypass_rls(db):
        return db.scalar(q) or Decimal("0")


def _effective_limit(b: Budget, now: datetime) -> Decimal:
    base = b.limit_usd
    if b.grace_extension_usd and b.grace_expires_at and now <= b.grace_expires_at:
        return base + b.grace_extension_usd
    return base


def _fire_alerts(
    db: Session,
    *,
    budget: Budget,
    threshold_pct: int,
    amount_usd: Decimal,
    period_start: datetime,
    period_end: datetime,
) -> bool:
    """Insert one BudgetAlert row idempotently. Returns True on first fire."""
    existing = db.scalars(
        select(BudgetAlert).where(
            BudgetAlert.budget_id == budget.id,
            BudgetAlert.period_start == period_start,
            BudgetAlert.threshold_pct == threshold_pct,
        )
    ).first()
    if existing is not None:
        return False
    alert = BudgetAlert(
        org_id=budget.org_id,
        budget_id=budget.id,
        threshold_pct=threshold_pct,
        amount_usd=amount_usd,
        period_start=period_start,
        period_end=period_end,
    )
    db.add(alert)
    db.flush()
    return True


def _emit_threshold_webhook(
    budget: Budget,
    *,
    threshold_pct: int,
    spent_usd: Decimal,
    effective_limit_usd: Decimal,
) -> None:
    """Stub: forward to control_plane.emit_webhook once wired up."""
    try:
        from ai_portal.control_plane.webhook_stub import emit_webhook  # type: ignore[import]
    except Exception:  # pragma: no cover - module not yet present
        return
    emit_webhook(
        event_type="budget.threshold",
        payload={
            "budget_id": budget.id,
            "budget_name": budget.name,
            "threshold_pct": threshold_pct,
            "spent_usd": str(spent_usd),
            "effective_limit_usd": str(effective_limit_usd),
            "scope_kind": budget.scope_kind,
            "scope_id": budget.scope_id,
        },
        org_id=budget.org_id,
    )


def check_budget(
    db: Session,
    *,
    org_id: _uuid.UUID,
    incoming_cost_usd: Decimal,
    user_id: int | None = None,
    api_key_id: int | None = None,
    team_id: int | None = None,
    now: datetime | None = None,
) -> BudgetDecision:
    """Check all budgets matching the actor scopes. Most-restrictive wins."""
    now = now or datetime.now(timezone.utc)
    incoming_cost_usd = Decimal(incoming_cost_usd)

    with bypass_rls(db):
        budgets = db.scalars(
            select(Budget).where(
                Budget.org_id == org_id,
                Budget.disabled_at.is_(None),
            )
        ).all()

    if not budgets:
        return BudgetDecision(
            action="allow",
            spent_usd=Decimal("0"),
            effective_limit_usd=Decimal("0"),
            used_pct=0.0,
        )

    decision: BudgetDecision = BudgetDecision(
        action="allow",
        spent_usd=Decimal("0"),
        effective_limit_usd=Decimal("0"),
        used_pct=0.0,
    )

    for b in budgets:
        if not _matches_scope(
            b.scope_kind, b.scope_id,
            user_id=user_id, api_key_id=api_key_id, team_id=team_id,
        ):
            continue

        start, end = _period_window(
            b.period, now=now, custom_start=b.period_start, custom_end=b.period_end,
        )
        spent = _spent_usd(
            db, org_id=org_id, scope_kind=b.scope_kind, scope_id=b.scope_id,
            period_start=start, period_end=end,
        )
        projected = spent + incoming_cost_usd
        eff_limit = _effective_limit(b, now)
        used_pct = float(projected / eff_limit * 100) if eff_limit > 0 else 0.0

        # Fire warn alerts for every threshold crossed by ``projected``.
        fired: list[int] = []
        for pct in sorted(b.warn_at_pcts):
            crossed = projected >= (eff_limit * Decimal(pct) / Decimal("100"))
            if crossed:
                if _fire_alerts(
                    db, budget=b, threshold_pct=pct, amount_usd=projected,
                    period_start=start, period_end=end,
                ):
                    fired.append(pct)
                    if b.webhook_on_threshold:
                        _emit_threshold_webhook(
                            b, threshold_pct=pct, spent_usd=projected, effective_limit_usd=eff_limit,
                        )

        # Hard cutoff at 100 %: caller must abort the action.
        if b.hard_cutoff and projected > eff_limit:
            return BudgetDecision(
                action="block",
                spent_usd=spent,
                effective_limit_usd=eff_limit,
                used_pct=used_pct,
                fired_thresholds=tuple(fired),
                reason=(
                    f"budget '{b.name}' exceeded: "
                    f"${projected} > ${eff_limit} this {b.period}"
                ),
            )
        action = "warn" if fired else (decision.action if decision.action == "warn" else "allow")
        # Reflect the most-constrained matched budget in the decision.
        if decision.effective_limit_usd == Decimal("0") or eff_limit < decision.effective_limit_usd:
            decision = BudgetDecision(
                action=action,
                spent_usd=spent,
                effective_limit_usd=eff_limit,
                used_pct=used_pct,
                fired_thresholds=tuple(fired) if fired else decision.fired_thresholds,
            )
        elif action == "warn":
            decision = BudgetDecision(
                action="warn",
                spent_usd=decision.spent_usd,
                effective_limit_usd=decision.effective_limit_usd,
                used_pct=decision.used_pct,
                fired_thresholds=tuple(fired),
            )

    return decision


# ── Grace-period extension API ──────────────────────────────────────────────


def extend_budget_grace(
    db: Session,
    *,
    budget_id: int,
    grace_extension_usd: Decimal,
    grace_expires_at: datetime,
) -> Budget:
    b = db.get(Budget, budget_id)
    if b is None:
        raise LookupError(f"budget {budget_id} not found")
    b.grace_extension_usd = grace_extension_usd
    b.grace_expires_at = grace_expires_at
    db.flush()
    return b
