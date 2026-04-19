"""Admin usage API — /api/admin/usage/*"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.core.db.rls import bypass_rls, set_org_context
from ai_portal.usage.model import MessageUsage
from ai_portal.usage.schemas import (
    ConversationUsageResponse,
    MyUsageResponse,
    UsageSummaryResponse,
    UsageSummaryRow,
)
from ai_portal.usage.service import _period_start, _seconds_to_period_end, check_quota

router = APIRouter(prefix="/api/admin/usage", tags=["usage"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, ("admin", "owner"))
    return user


@router.get("/summary", response_model=UsageSummaryResponse)
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
            label_col = func.cast(MessageUsage.user_id, type_=None).label("group_key")
        elif group_by == "capability":
            label_col = func.coalesce(
                MessageUsage.capability_flags.cast(type_=None), "unknown"
            ).label("group_key")
        else:
            label_col = func.coalesce(MessageUsage.api_model_id, "unknown").label("group_key")

        rows = db.execute(
            select(
                label_col,
                func.coalesce(func.sum(MessageUsage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(MessageUsage.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(MessageUsage.cached_input_tokens), 0).label("cached_input_tokens"),
                func.coalesce(func.sum(MessageUsage.cost_usd), Decimal("0")).label("cost_usd"),
                func.count().label("message_count"),
            ).where(
                MessageUsage.org_id == user.org_id,
                MessageUsage.created_at >= effective_start,
                MessageUsage.created_at < effective_end,
            ).group_by(label_col)
        ).all()

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


@router.get("/by-conversation/{conversation_id}", response_model=ConversationUsageResponse)
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
                func.coalesce(func.sum(MessageUsage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(MessageUsage.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(MessageUsage.cached_input_tokens), 0).label("cached_input_tokens"),
                func.coalesce(func.sum(MessageUsage.cost_usd), Decimal("0")).label("cost_usd"),
                func.count().label("message_count"),
            ).where(
                MessageUsage.org_id == user.org_id,
                MessageUsage.conversation_id == conversation_id,
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

    from ai_portal.usage.service import _period_end  # noqa: PLC0415

    period_start = _period_start(period)
    period_end_dt = _period_end(period)

    with bypass_rls(db):
        row = db.execute(
            select(
                func.coalesce(func.sum(MessageUsage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(MessageUsage.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(MessageUsage.cost_usd), Decimal("0")).label("cost_usd"),
                func.count().label("message_count"),
            ).where(
                MessageUsage.org_id == user.org_id,
                MessageUsage.user_id == user.id,
                MessageUsage.created_at >= period_start,
            )
        ).one()

    # Check if user has a quota for context.
    quota_max: Decimal | None = None
    quota_pct: float | None = None
    quotas = db.scalars(
        select(MessageUsage)
        .where(MessageUsage.org_id == user.org_id)
        .limit(0)
    ).all()  # warm up RLS context then use separate query
    from ai_portal.usage.model import UsageQuota  # noqa: PLC0415
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
