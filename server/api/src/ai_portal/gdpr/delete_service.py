"""Delete job lifecycle — submit + fetch (sync DB layer)."""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from sqlalchemy.orm import Session

from ai_portal.core.db.rls import bypass_rls
from ai_portal.gdpr.model import DataDeleteJob


def submit_delete(
    db: Session,
    *,
    org_id: _uuid.UUID,
    scope: dict[str, Any],
) -> DataDeleteJob:
    """Insert a new delete job in ``queued`` status. Commits the transaction."""
    job = DataDeleteJob(
        org_id=org_id,
        scope_json=dict(scope or {}),
        status="queued",
    )
    with bypass_rls(db):
        db.add(job)
        db.commit()
        db.refresh(job)
    return job


def get_delete(
    db: Session, *, org_id: _uuid.UUID, job_id: _uuid.UUID
) -> DataDeleteJob | None:
    """Return the job row if it belongs to ``org_id``; else ``None``."""
    with bypass_rls(db):
        row = db.get(DataDeleteJob, job_id)
    if row is None or row.org_id != org_id:
        return None
    return row
