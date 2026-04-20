from __future__ import annotations
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.auth.deps import get_current_user
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.core.db.session import get_async_db
from ai_portal.usage import consumption_service
from ai_portal.usage.consumption_schemas import (
    SummaryResponse, ThreadsResponse, TimelineResponse, TrendResponse,
)

router = APIRouter(prefix="/api/admin/consumption", tags=["admin-consumption"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, "admin", "owner")
    return user


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    start: datetime = Query(...),
    end: datetime = Query(...),
    session: AsyncSession = Depends(get_async_db),
    user: User = Depends(_require_admin),
) -> SummaryResponse:
    return await consumption_service.summary(
        session=session, org_id=user.org_id, start=start, end=end
    )


@router.get("/trend", response_model=TrendResponse)
async def get_trend(
    start: datetime = Query(...),
    end: datetime = Query(...),
    grain: Literal["day", "hour"] = Query("day"),
    by: Literal["kind", "provider"] = Query("kind"),
    session: AsyncSession = Depends(get_async_db),
    user: User = Depends(_require_admin),
) -> TrendResponse:
    return await consumption_service.trend(
        session=session, org_id=user.org_id, start=start, end=end, grain=grain, by=by
    )


@router.get("/threads", response_model=ThreadsResponse)
async def get_threads(
    start: datetime = Query(...),
    end: datetime = Query(...),
    user_id: int | None = Query(None),
    model: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    session: AsyncSession = Depends(get_async_db),
    user: User = Depends(_require_admin),
) -> ThreadsResponse:
    return await consumption_service.threads(
        session=session, org_id=user.org_id, start=start, end=end,
        user_id=user_id, model=model, page=page, page_size=page_size,
    )


@router.get("/threads/{thread_id}/timeline", response_model=TimelineResponse)
async def get_timeline(
    thread_id: int,
    session: AsyncSession = Depends(get_async_db),
    user: User = Depends(_require_admin),
) -> TimelineResponse:
    return await consumption_service.timeline(
        session=session, org_id=user.org_id, thread_id=thread_id
    )
