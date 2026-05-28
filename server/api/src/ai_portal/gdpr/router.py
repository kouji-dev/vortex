"""GDPR routes — /v1/data-export, /v1/data-delete.

Endpoints (org-scoped):

- ``POST /v1/data-export``         — submit an Article 15 export job
- ``GET  /v1/data-export/{job_id}``— fetch job status + result_url
- ``POST /v1/data-delete``         — submit an Article 17 delete job
- ``GET  /v1/data-delete/{job_id}``— fetch delete job status

Both POSTs return the queued job immediately; a background worker handles
the heavy lifting and updates the row. Polling the GET endpoint is the
client contract for completion.
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.control_plane.deps import require_permission
from ai_portal.gdpr.delete_service import get_delete, submit_delete
from ai_portal.gdpr.export_service import get_export, submit_export
from ai_portal.gdpr.model import DataDeleteJob, DataExportJob
from ai_portal.gdpr.schemas import (
    DataDeleteCreate,
    DataDeleteJobOut,
    DataExportCreate,
    DataExportJobOut,
)
from ai_portal.rbac.service import Actor

router = APIRouter(prefix="/v1", tags=["gdpr"])


# ── helpers ─────────────────────────────────────────────────────────────────


def _export_out(row: DataExportJob) -> DataExportJobOut:
    return DataExportJobOut(
        id=row.id,
        org_id=row.org_id,
        requested_by=row.requested_by,
        status=row.status,
        result_url=row.result_url,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
    )


def _delete_out(row: DataDeleteJob) -> DataDeleteJobOut:
    return DataDeleteJobOut(
        id=row.id,
        org_id=row.org_id,
        scope_json=dict(row.scope_json or {}),
        status=row.status,
        requested_at=row.requested_at,
        completed_at=row.completed_at,
    )


# ── Export ──────────────────────────────────────────────────────────────────


@router.post(
    "/data-export",
    response_model=DataExportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_data_export(
    body: DataExportCreate,
    actor: Actor = Depends(require_permission("data:export")),
    db: Session = Depends(get_db),
) -> DataExportJobOut:
    job = submit_export(
        db,
        org_id=actor.org_id,
        requested_by=actor.user_id,
    )
    return _export_out(job)


@router.get("/data-export/{job_id}", response_model=DataExportJobOut)
def get_data_export(
    job_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("data:export")),
    db: Session = Depends(get_db),
) -> DataExportJobOut:
    row = get_export(db, org_id=actor.org_id, job_id=job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="export job not found")
    return _export_out(row)


# ── Delete ──────────────────────────────────────────────────────────────────


@router.post(
    "/data-delete",
    response_model=DataDeleteJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_data_delete(
    body: DataDeleteCreate,
    actor: Actor = Depends(require_permission("data:delete")),
    db: Session = Depends(get_db),
) -> DataDeleteJobOut:
    scope = dict(body.scope or {})
    # Normalise: org-subject jobs always carry the actor's org_id.
    if scope.get("subject") == "org":
        scope["org_id"] = str(actor.org_id)
    job = submit_delete(db, org_id=actor.org_id, scope=scope)
    return _delete_out(job)


@router.get("/data-delete/{job_id}", response_model=DataDeleteJobOut)
def get_data_delete(
    job_id: _uuid.UUID,
    actor: Actor = Depends(require_permission("data:delete")),
    db: Session = Depends(get_db),
) -> DataDeleteJobOut:
    row = get_delete(db, org_id=actor.org_id, job_id=job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="delete job not found")
    return _delete_out(row)
