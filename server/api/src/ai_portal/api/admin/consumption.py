from __future__ import annotations
from datetime import datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.usage import consumption_service
from ai_portal.usage.consumption_schemas import (
    SummaryResponse, ThreadsResponse, TimelineResponse, TrendResponse,
)

router = APIRouter(prefix="/api/admin/consumption", tags=["admin-consumption"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, "admin", "owner")
    return user


def _normalize_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Coerce both ends to UTC-aware datetimes.

    Frontend sends ``YYYY-MM-DD`` (date-only); FastAPI parses that as midnight
    of the local naïve clock, which silently dropped everything that happened
    on the end day (since ``last_message_at <= 'YYYY-MM-DD 00:00:00'`` excludes
    any time later that day). Date-only payloads now expand to
    ``[start 00:00:00 UTC, end 23:59:59.999999 UTC]``; full datetimes pass
    through but get tagged UTC when naïve.
    """
    def _to_utc(dt: datetime, *, is_end: bool) -> datetime:
        if dt.tzinfo is None:
            # Date-only inputs arrive as midnight; promote the end-of-day side.
            if is_end and dt.time() == time(0, 0, 0):
                dt = datetime.combine(dt.date(), time(23, 59, 59, 999_999))
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return _to_utc(start, is_end=False), _to_utc(end, is_end=True)


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    start: datetime = Query(...),
    end: datetime = Query(...),
    session: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> SummaryResponse:
    start, end = _normalize_range(start, end)
    return consumption_service.summary(
        session=session, org_id=user.org_id, start=start, end=end
    )


@router.get("/trend", response_model=TrendResponse)
def get_trend(
    start: datetime = Query(...),
    end: datetime = Query(...),
    grain: Literal["day", "hour"] = Query("day"),
    by: Literal["kind", "provider"] = Query("kind"),
    session: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> TrendResponse:
    start, end = _normalize_range(start, end)
    return consumption_service.trend(
        session=session, org_id=user.org_id, start=start, end=end, grain=grain, by=by
    )


@router.get("/threads", response_model=ThreadsResponse)
def get_threads(
    start: datetime = Query(...),
    end: datetime = Query(...),
    user_id: int | None = Query(None),
    model: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    session: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> ThreadsResponse:
    start, end = _normalize_range(start, end)
    return consumption_service.threads(
        session=session, org_id=user.org_id, start=start, end=end,
        user_id=user_id, model=model, page=page, page_size=page_size,
    )


@router.get("/threads/{thread_id}/timeline", response_model=TimelineResponse)
def get_timeline(
    thread_id: int,
    session: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> TimelineResponse:
    return consumption_service.timeline(
        session=session, org_id=user.org_id, thread_id=thread_id
    )
