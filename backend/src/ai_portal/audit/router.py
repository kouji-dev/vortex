"""Admin audit log API — /api/admin/audit/*"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.audit.model import AuditEvent
from ai_portal.audit.schemas import AuditEventResponse, AuditEventsResponse
from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.core.db.rls import bypass_rls

router = APIRouter(prefix="/api/admin/audit", tags=["audit"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, ("admin", "owner"))
    return user


@router.get("", response_model=AuditEventsResponse)
def list_audit_events(
    event_type: str | None = Query(None),
    resource_type: str | None = Query(None),
    actor_user_id: int | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> AuditEventsResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    with bypass_rls(db):
        q = select(AuditEvent).where(AuditEvent.org_id == user.org_id)
        if event_type:
            q = q.where(AuditEvent.event_type == event_type)
        if resource_type:
            q = q.where(AuditEvent.resource_type == resource_type)
        if actor_user_id is not None:
            q = q.where(AuditEvent.actor_user_id == actor_user_id)
        if start:
            q = q.where(AuditEvent.created_at >= start)
        if end:
            q = q.where(AuditEvent.created_at < end)

        total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
        events = db.scalars(q.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)).all()

    return AuditEventsResponse(
        total=total,
        items=[
            AuditEventResponse(
                id=e.id,
                org_id=e.org_id,
                actor_user_id=e.actor_user_id,
                actor_type=e.actor_type,
                event_type=e.event_type,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                action=e.action,
                metadata=e.metadata_,
                request_id=e.request_id,
                ip_address=str(e.ip_address) if e.ip_address else None,
                user_agent=e.user_agent,
                created_at=e.created_at,
            )
            for e in events
        ],
    )


@router.get("/export")
def export_audit_events(
    fmt: Literal["jsonl", "csv"] = Query("jsonl"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> StreamingResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    import csv  # noqa: PLC0415
    import io  # noqa: PLC0415
    import json  # noqa: PLC0415

    with bypass_rls(db):
        q = select(AuditEvent).where(AuditEvent.org_id == user.org_id)
        if start:
            q = q.where(AuditEvent.created_at >= start)
        if end:
            q = q.where(AuditEvent.created_at < end)
        events = db.scalars(q.order_by(AuditEvent.created_at.asc())).all()

    def _jsonl_gen():
        for e in events:
            yield json.dumps({
                "id": e.id,
                "org_id": str(e.org_id),
                "actor_user_id": e.actor_user_id,
                "event_type": e.event_type,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "action": e.action,
                "created_at": e.created_at.isoformat(),
            }) + "\n"

    def _csv_gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "org_id", "actor_user_id", "event_type", "resource_type", "resource_id", "action", "created_at"])
        yield buf.getvalue()
        for e in events:
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([e.id, str(e.org_id), e.actor_user_id, e.event_type, e.resource_type, e.resource_id, e.action, e.created_at.isoformat()])
            yield buf.getvalue()

    if fmt == "csv":
        return StreamingResponse(_csv_gen(), media_type="text/csv",
                                  headers={"Content-Disposition": "attachment; filename=audit.csv"})
    return StreamingResponse(_jsonl_gen(), media_type="application/x-ndjson",
                              headers={"Content-Disposition": "attachment; filename=audit.jsonl"})
