"""Usage domain service — write path and quota enforcement."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.usage.model import MessageUsage, UsageQuota
from ai_portal.usage.pricing import compute_cost_usd


_PROVIDER_FROM_MODEL: dict[str, str] = {
    "claude": "anthropic",
    "gemini": "google",
    "gpt": "openai",
    "o3": "openai",
    "o4": "openai",
}


def _infer_provider(api_model_id: str) -> str:
    m = (api_model_id or "").lower()
    for prefix, provider in _PROVIDER_FROM_MODEL.items():
        if m.startswith(prefix) or f"-{prefix}-" in m or m.startswith(f"anthropic-{prefix}"):
            return provider
    return "unknown"


def record_usage(
    db: Session,
    *,
    org_id: uuid.UUID,
    user_id: int | None,
    conversation_id: int | None,
    message_id: int | None,
    api_model_id: str,
    usage: dict[str, Any],
    latency_ms: int | None = None,
    tool_calls_count: int = 0,
    capability_flags: dict | None = None,
) -> MessageUsage:
    """Write one ``message_usage`` row synchronously in the caller's transaction.

    Called from ``streaming_service._record_usage_async`` which opens its own
    session, so no RLS context is set here — the worker session bypasses RLS.
    """
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    cached = int(usage.get("cached_input_tokens", 0) or 0)
    cache_creation = int(usage.get("cache_creation_input_tokens", 0) or 0)
    reasoning = usage.get("reasoning_tokens")

    cost = compute_cost_usd(
        api_model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        cache_creation_input_tokens=cache_creation,
    )

    row = MessageUsage(
        org_id=org_id,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        api_model_id=api_model_id,
        provider=_infer_provider(api_model_id),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        cache_creation_input_tokens=cache_creation,
        reasoning_tokens=reasoning,
        tool_calls_count=tool_calls_count,
        latency_ms=latency_ms,
        cost_usd=cost,
        capability_flags=capability_flags,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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

    quotas = db.scalars(
        select(UsageQuota).where(
            UsageQuota.org_id == org_id,
            UsageQuota.user_id.in_([user_id, None]),
        )
    ).all()

    if not quotas:
        return QuotaDecision("allow")

    for quota in quotas:
        # Skip if quota is for a different model.
        if quota.api_model_id and quota.api_model_id != api_model_id:
            continue
        # Skip if quota is for a different user.
        if quota.user_id and quota.user_id != user_id:
            continue

        period_start = _period_start(quota.period)

        # Sum actual usage for this period.
        with bypass_rls(db):
            row = db.execute(
                select(
                    func.coalesce(func.sum(MessageUsage.cost_usd), Decimal("0")).label("cost"),
                    func.coalesce(func.sum(MessageUsage.input_tokens), 0).label("input_tokens"),
                    func.coalesce(func.sum(MessageUsage.output_tokens), 0).label("output_tokens"),
                ).where(
                    MessageUsage.org_id == org_id,
                    MessageUsage.user_id == user_id,
                    MessageUsage.created_at >= period_start,
                    *(
                        [MessageUsage.api_model_id == api_model_id]
                        if quota.api_model_id
                        else []
                    ),
                )
            ).one()

        current_cost: Decimal = row.cost or Decimal("0")
        current_input: int = row.input_tokens or 0
        current_output: int = row.output_tokens or 0

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
