"""Usage domain service — quota enforcement."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from ai_portal.usage.model import UsageQuota
from ai_portal.chat.model import Thread, ThreadItem
from ai_portal.chat.item_kinds import ItemKind


class QuotaDecision:
    def __init__(self, action: str, reason: str = "", retry_after_seconds: int | None = None) -> None:
        self.action = action  # "allow" | "warn" | "block"
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds

    @property
    def is_blocked(self) -> bool:
        return self.action == "block"


def _period_start(period: str) -> datetime:
    now = datetime.now(UTC)
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    # month
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _period_end(period: str) -> datetime:
    from datetime import timedelta
    start = _period_start(period)
    if period == "day":
        return start + timedelta(days=1)
    # month: advance to first of next month
    year = start.year + (start.month // 12)
    month = (start.month % 12) + 1
    return start.replace(year=year, month=month, day=1)


def _seconds_to_period_end(period: str) -> int:
    end = _period_end(period)
    delta = end - datetime.now(UTC)
    return max(int(delta.total_seconds()), 0)


def check_quota(
    db: Session,
    *,
    org_id: uuid.UUID,
    user_id: int,
    api_model_id: str,
) -> QuotaDecision:
    """Check all applicable quotas. Returns a QuotaDecision to the caller.

    Checked in order: model-specific → any-model. More specific quota wins.
    """
    from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415

    # Fix 1: use OR to match org-level quotas (user_id IS NULL) correctly.
    # IN (..., NULL) never matches NULL rows in SQL.
    quotas = db.scalars(
        select(UsageQuota).where(
            UsageQuota.org_id == org_id,
            (UsageQuota.user_id == user_id) | (UsageQuota.user_id.is_(None)),
        )
    ).all()

    if not quotas:
        return QuotaDecision("allow")

    # Fix 2 & 3: precompute usage once per unique period (eliminates N+1).
    # Each query covers the full period window [start, end) with an upper bound.
    periods = {q.period for q in quotas}
    usage_by_period: dict[str, dict] = {}
    for period in periods:
        ps = _period_start(period)
        pe = _period_end(period)
        with bypass_rls(db):
            row = db.execute(
                select(
                    func.coalesce(func.sum(ThreadItem.cost_usd), Decimal("0")).label("cost"),
                    func.coalesce(func.sum(cast(ThreadItem.data["input_tokens"].astext, Integer)), 0).label("input_tokens"),
                    func.coalesce(func.sum(cast(ThreadItem.data["output_tokens"].astext, Integer)), 0).label("output_tokens"),
                )
                .join(Thread, Thread.id == ThreadItem.thread_id)
                .where(
                    ThreadItem.org_id == org_id,
                    ThreadItem.kind == ItemKind.llm_call,
                    ThreadItem.created_at >= ps,
                    ThreadItem.created_at < pe,
                    Thread.user_id == user_id,
                )
            ).one()
        usage_by_period[period] = {
            "cost": row.cost or Decimal("0"),
            "input_tokens": row.input_tokens or 0,
            "output_tokens": row.output_tokens or 0,
        }

    for quota in quotas:
        # Skip if quota is for a different model.
        if quota.api_model_id and quota.api_model_id != api_model_id:
            continue
        # Skip if quota is for a different user.
        if quota.user_id and quota.user_id != user_id:
            continue

        usage = usage_by_period[quota.period]
        current_cost: Decimal = usage["cost"]
        current_input: int = usage["input_tokens"]
        current_output: int = usage["output_tokens"]

        breached = False
        reason = ""

        if quota.max_cost_usd is not None and current_cost >= quota.max_cost_usd:
            breached = True
            reason = f"Cost quota exceeded: ${current_cost:.4f} / ${quota.max_cost_usd:.4f} USD this {quota.period}"
        elif quota.max_input_tokens is not None and current_input >= quota.max_input_tokens:
            breached = True
            reason = f"Input token quota exceeded: {current_input:,} / {quota.max_input_tokens:,} this {quota.period}"
        elif quota.max_output_tokens is not None and current_output >= quota.max_output_tokens:
            breached = True
            reason = f"Output token quota exceeded: {current_output:,} / {quota.max_output_tokens:,} this {quota.period}"

        if breached:
            return QuotaDecision(
                action=quota.action_on_breach,
                reason=reason,
                retry_after_seconds=_seconds_to_period_end(quota.period),
            )

    return QuotaDecision("allow")
