"""Admin audit log API — /api/admin/audit/*

Endpoints:
- ``GET    /api/admin/audit``                  search
- ``GET    /api/admin/audit/export``           streaming download (jsonl/csv)
- ``POST   /api/admin/audit/export``           enqueue export to S3 / SIEM
- ``GET    /api/admin/audit/export/{job_id}``  poll job
- ``GET    /api/admin/audit/integrity``        verify hash chain
- ``GET    /api/admin/audit/retention``        read retention + sinks config
- ``PUT    /api/admin/audit/retention``        update retention + sinks config
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_portal.audit.chain import verify_chain
from ai_portal.audit.event_view import decrypt_metadata
from ai_portal.audit.export_service import (
    count_events,
    query_events,
    stream_csv,
    stream_for_export,
    stream_jsonl,
)
from ai_portal.audit.protocol import AuditFilter
from ai_portal.audit.repository import AuditRepository
from ai_portal.audit.schemas import AuditEventResponse, AuditEventsResponse
from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.core.db.rls import bypass_rls

router = APIRouter(prefix="/api/admin/audit", tags=["audit"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, ("admin", "owner"))
    return user


def _filter_from_query(
    *,
    org_id,
    event_type: str | None,
    resource_type: str | None,
    actor_user_id: int | None,
    action: str | None,
    start: datetime | None,
    end: datetime | None,
    limit: int,
    offset: int,
) -> AuditFilter:
    return AuditFilter(
        org_id=org_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        resource_type=resource_type,
        action=action,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@router.get("", response_model=AuditEventsResponse)
def list_audit_events(
    event_type: str | None = Query(None),
    resource_type: str | None = Query(None),
    actor_user_id: int | None = Query(None),
    action: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> AuditEventsResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    f = _filter_from_query(
        org_id=user.org_id,
        event_type=event_type,
        resource_type=resource_type,
        actor_user_id=actor_user_id,
        action=action,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )

    with bypass_rls(db):
        total = count_events(db, user.org_id, f)
        events = query_events(db, user.org_id, f)

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
                metadata=decrypt_metadata(e),
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
    event_type: str | None = Query(None),
    resource_type: str | None = Query(None),
    actor_user_id: int | None = Query(None),
    action: str | None = Query(None),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> StreamingResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")

    f = _filter_from_query(
        org_id=user.org_id,
        event_type=event_type,
        resource_type=resource_type,
        actor_user_id=actor_user_id,
        action=action,
        start=start,
        end=end,
        limit=10_000_000,
        offset=0,
    )

    with bypass_rls(db):
        events = stream_for_export(db, user.org_id, f)

    if fmt == "csv":
        return StreamingResponse(
            stream_csv(events),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit.csv"},
        )
    return StreamingResponse(
        stream_jsonl(events),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=audit.jsonl"},
    )


class ExportJobRequest(BaseModel):
    fmt: Literal["jsonl", "csv"] = "jsonl"
    destination: Literal["s3", "siem"] = "s3"
    filter: dict | None = None


class ExportJobResponse(BaseModel):
    id: int
    status: str
    fmt: str
    destination: str
    blob_url: str | None = None
    error: str | None = None


@router.post("/export", response_model=ExportJobResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_export_job(
    req: ExportJobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> ExportJobResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    repo = AuditRepository(db)
    with bypass_rls(db):
        job = repo.create_export_job(
            org_id=user.org_id,
            requested_by=user.id,
            fmt=req.fmt,
            destination=req.destination,
            filter_json=req.filter,
        )
        db.commit()
    return ExportJobResponse(
        id=job.id,
        status=job.status,
        fmt=job.fmt,
        destination=job.destination,
        blob_url=job.blob_url,
        error=job.error,
    )


@router.get("/export/{job_id}", response_model=ExportJobResponse)
def get_export_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> ExportJobResponse:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    repo = AuditRepository(db)
    with bypass_rls(db):
        job = repo.get_export_job(user.org_id, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return ExportJobResponse(
        id=job.id,
        status=job.status,
        fmt=job.fmt,
        destination=job.destination,
        blob_url=job.blob_url,
        error=job.error,
    )


@router.get("/integrity")
def verify_integrity(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> dict:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    repo = AuditRepository(db)
    with bypass_rls(db):
        events = repo.list_by_org(user.org_id, limit=100_000)
    ok, bad = verify_chain(events)
    return {"ok": ok, "checked": len(events), "first_bad_index": bad}


class RetentionConfigDTO(BaseModel):
    retention_days: int = Field(ge=1, le=10_000)
    sink_configs: list[dict] = Field(default_factory=list)


@router.get("/retention", response_model=RetentionConfigDTO)
def read_retention(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> RetentionConfigDTO:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    repo = AuditRepository(db)
    with bypass_rls(db):
        cfg = repo.get_retention_config(user.org_id)
    if cfg is None:
        return RetentionConfigDTO(retention_days=2555, sink_configs=[])
    return RetentionConfigDTO(retention_days=cfg.retention_days, sink_configs=cfg.sink_configs)


@router.put("/retention", response_model=RetentionConfigDTO)
def update_retention(
    dto: RetentionConfigDTO,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> RetentionConfigDTO:
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org")
    repo = AuditRepository(db)
    with bypass_rls(db):
        cfg = repo.upsert_retention_config(
            user.org_id,
            retention_days=dto.retention_days,
            sink_configs=dto.sink_configs,
        )
        db.commit()
    return RetentionConfigDTO(retention_days=cfg.retention_days, sink_configs=cfg.sink_configs)
