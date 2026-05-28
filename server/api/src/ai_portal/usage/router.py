"""Admin usage API — /api/admin/usage/*"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.core.db.rls import bypass_rls, set_org_context
from ai_portal.chat.model import Thread, ThreadItem
from ai_portal.chat.item_kinds import ItemKind
from ai_portal.usage.schemas import (
    ConversationUsageResponse,
    MyUsageResponse,
    UsageDashboardResponse,
    UsageDashboardRow,
    UsageSummaryResponse,
    UsageSummaryRow,
)
from ai_portal.usage.model import UsageQuota
from ai_portal.usage.rollups import Dim, Grain, aggregate
from ai_portal.usage.service import _period_end, _period_start, _seconds_to_period_end, check_quota

router = APIRouter(prefix="/api/admin/usage", tags=["usage"])

v1_router = APIRouter(prefix="/v1/usage", tags=["usage"])


_GRAIN_FOR_PERIOD: dict[str, Grain] = {
    "hour": "hour",
    "day": "day",
    "month": "month",
}


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, ("admin", "owner"))
    return user


@v1_router.get("", response_model=UsageDashboardResponse)
def get_usage_dashboard(
    dim: str = Query("model", pattern=r"^(user|team|key|model|module|unit)$"),
    period: str = Query("day", pattern=r"^(hour|day|month)$"),
    period_start: datetime | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> UsageDashboardResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    grain = _GRAIN_FOR_PERIOD[period]
    if period_start is None:
        now = datetime.now(UTC)
        if grain == "hour":
            period_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        elif grain == "day":
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    with bypass_rls(db):
        set_org_context(db, user.org_id)
        buckets = aggregate(
            db, org_id=user.org_id, grain=grain, dim=dim, period_start=period_start  # type: ignore[arg-type]
        )

    if not buckets:
        return UsageDashboardResponse(
            dim=dim,
            grain=grain,
            period_start=period_start,
            period_end=period_start,
            rows=[],
            total_cost_usd=Decimal("0"),
            total_qty=Decimal("0"),
        )

    rows = [
        UsageDashboardRow(
            dim_value=b.dim_value,
            qty=b.qty,
            cost_usd=b.cost_usd,
            event_count=b.event_count,
        )
        for b in buckets
    ]
    total_cost = sum((b.cost_usd for b in buckets), Decimal("0"))
    total_qty = sum((b.qty for b in buckets), Decimal("0"))
    # All buckets share the same window — derive period_end from grain.
    from ai_portal.usage.rollups import _next_period  # noqa: PLC0415
    return UsageDashboardResponse(
        dim=dim,
        grain=grain,
        period_start=buckets[0].period_start,
        period_end=_next_period(buckets[0].period_start, grain),
        rows=rows,
        total_cost_usd=total_cost,
        total_qty=total_qty,
    )


@router.get("/summary", response_model=UsageSummaryResponse, deprecated=True)
def get_usage_summary(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    group_by: str = Query("model"),
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> UsageSummaryResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    now = datetime.now(UTC)
    effective_end = end or now
    effective_start = start or (now - timedelta(days=30))

    with bypass_rls(db):
        set_org_context(db, user.org_id)

        if group_by == "user":
            label_col = Thread.user_id.label("group_key")
        else:
            label_col = func.coalesce(ThreadItem.model, "unknown").label("group_key")

        base_stmt = (
            select(
                label_col,
                func.coalesce(func.sum(cast(ThreadItem.data["input_tokens"].astext, Integer)), 0).label("input_tokens"),
                func.coalesce(func.sum(cast(ThreadItem.data["output_tokens"].astext, Integer)), 0).label("output_tokens"),
                func.coalesce(func.sum(cast(ThreadItem.data["cached_input_tokens"].astext, Integer)), 0).label("cached_input_tokens"),
                func.coalesce(func.sum(ThreadItem.cost_usd), Decimal("0")).label("cost_usd"),
                func.count().label("message_count"),
            )
            .join(Thread, Thread.id == ThreadItem.thread_id)
            .where(
                ThreadItem.org_id == user.org_id,
                ThreadItem.kind == ItemKind.llm_call,
                ThreadItem.created_at >= effective_start,
                ThreadItem.created_at < effective_end,
            )
            .group_by(label_col)
        )
        rows = db.execute(base_stmt).all()

    summary_rows = [
        UsageSummaryRow(
            group_key=str(r.group_key or "unknown"),
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            cached_input_tokens=r.cached_input_tokens,
            cost_usd=r.cost_usd,
            message_count=r.message_count,
        )
        for r in rows
    ]
    total_cost = sum((r.cost_usd for r in summary_rows), Decimal("0"))
    total_msgs = sum(r.message_count for r in summary_rows)

    return UsageSummaryResponse(
        start=effective_start,
        end=effective_end,
        group_by=group_by,
        rows=summary_rows,
        total_cost_usd=total_cost,
        total_messages=total_msgs,
    )


@router.get("/by-conversation/{conversation_id}", response_model=ConversationUsageResponse, deprecated=True)
def get_conversation_usage(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> ConversationUsageResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    with bypass_rls(db):
        row = db.execute(
            select(
                func.coalesce(func.sum(cast(ThreadItem.data["input_tokens"].astext, Integer)), 0).label("input_tokens"),
                func.coalesce(func.sum(cast(ThreadItem.data["output_tokens"].astext, Integer)), 0).label("output_tokens"),
                func.coalesce(func.sum(cast(ThreadItem.data["cached_input_tokens"].astext, Integer)), 0).label("cached_input_tokens"),
                func.coalesce(func.sum(ThreadItem.cost_usd), Decimal("0")).label("cost_usd"),
                func.count().label("message_count"),
            ).where(
                ThreadItem.org_id == user.org_id,
                ThreadItem.thread_id == conversation_id,
                ThreadItem.kind == ItemKind.llm_call,
            )
        ).one()

    return ConversationUsageResponse(
        conversation_id=conversation_id,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cached_input_tokens=row.cached_input_tokens,
        cost_usd=row.cost_usd,
        message_count=row.message_count,
    )


@router.get("/my", response_model=MyUsageResponse)
def get_my_usage(
    period: str = Query("month"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MyUsageResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    period_start = _period_start(period)
    period_end_dt = _period_end(period)

    with bypass_rls(db):
        row = db.execute(
            select(
                func.coalesce(func.sum(cast(ThreadItem.data["input_tokens"].astext, Integer)), 0).label("input_tokens"),
                func.coalesce(func.sum(cast(ThreadItem.data["output_tokens"].astext, Integer)), 0).label("output_tokens"),
                func.coalesce(func.sum(ThreadItem.cost_usd), Decimal("0")).label("cost_usd"),
                func.count().label("message_count"),
            )
            .join(Thread, Thread.id == ThreadItem.thread_id)
            .where(
                ThreadItem.org_id == user.org_id,
                ThreadItem.kind == ItemKind.llm_call,
                ThreadItem.created_at >= period_start,
                Thread.user_id == user.id,
            )
        ).one()

    # Check if user has a quota for context.
    quota_max: Decimal | None = None
    quota_pct: float | None = None
    with bypass_rls(db):
        user_quota = db.scalars(
            select(UsageQuota).where(
                UsageQuota.org_id == user.org_id,
                UsageQuota.user_id == user.id,
                UsageQuota.period == period,
                UsageQuota.max_cost_usd.is_not(None),
            ).limit(1)
        ).first()
    if user_quota and user_quota.max_cost_usd:
        quota_max = user_quota.max_cost_usd
        quota_pct = float(row.cost_usd / quota_max * 100) if quota_max else None

    return MyUsageResponse(
        period_start=period_start,
        period_end=period_end_dt,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cost_usd=row.cost_usd,
        message_count=row.message_count,
        quota_max_cost_usd=quota_max,
        quota_pct=quota_pct,
    )
