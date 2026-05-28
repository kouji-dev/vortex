"""Export job lifecycle — submit + fetch (sync DB layer).

The HTTP layer calls :func:`submit_export` to create a ``data_export_jobs``
row and returns it to the client. The worker (``export_worker``) consumes
the queued row asynchronously.
"""

from __future__ import annotations

import uuid as _uuid

from sqlalchemy.orm import Session

from ai_portal.core.db.rls import bypass_rls
from ai_portal.gdpr.model import DataExportJob


def submit_export(
    db: Session,
    *,
    org_id: _uuid.UUID,
    requested_by: int | None,
) -> DataExportJob:
    """Insert a new export job in ``queued`` status. Commits the transaction."""
    job = DataExportJob(
        org_id=org_id,
        requested_by=requested_by,
        status="queued",
    )
    with bypass_rls(db):
        db.add(job)
        db.commit()
        db.refresh(job)
    return job


def get_export(
    db: Session, *, org_id: _uuid.UUID, job_id: _uuid.UUID
) -> DataExportJob | None:
    """Return the job row if it belongs to ``org_id``; else ``None``."""
    with bypass_rls(db):
        row = db.get(DataExportJob, job_id)
    if row is None or row.org_id != org_id:
        return None
    return row
