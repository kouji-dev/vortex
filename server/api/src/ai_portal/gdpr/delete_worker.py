"""Delete worker — fans out registered deleters, emits audit event on success.

Flow per job:

- mark row ``running``
- iterate :mod:`ai_portal.gdpr.registry` deleters
- if any deleter raises → mark ``failed`` + ``completed_at`` and stop
  emitting audit (failed jobs do not log a deletion)
- on success: mark ``succeeded`` + ``completed_at`` and emit audit event
  ``gdpr.delete.completed`` with the scope and modules touched
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime

from ai_portal.audit.service import emit_audit
from ai_portal.gdpr.registry import list_deleters

logger = logging.getLogger(__name__)


async def run_delete_job(*, job_id: _uuid.UUID) -> None:
    """Execute one queued delete job."""
    from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415
    from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
    from ai_portal.gdpr.model import DataDeleteJob  # noqa: PLC0415

    db = SessionLocal()
    try:
        with bypass_rls(db):
            row = db.get(DataDeleteJob, job_id)
            if row is None:
                logger.warning("delete job %s not found", job_id)
                return
            org_id = row.org_id
            scope = dict(row.scope_json or {})
            row.status = "running"
            db.commit()

        deleters = list_deleters()
        failed_module: str | None = None
        last_error: str | None = None
        modules_touched: list[str] = []

        for module_name, fn in deleters.items():
            try:
                await fn(org_id, scope)
                modules_touched.append(module_name)
            except Exception as exc:  # noqa: BLE001
                logger.exception("deleter for %s raised: %s", module_name, exc)
                failed_module = module_name
                last_error = str(exc)
                break

        completed_at = datetime.now(tz=UTC)
        final_status = "failed" if failed_module is not None else "succeeded"

        with bypass_rls(db):
            row = db.get(DataDeleteJob, job_id)
            if row is not None:
                row.status = final_status
                row.completed_at = completed_at
                db.commit()

        if final_status == "succeeded":
            emit_audit(
                org_id=org_id,
                event_type="gdpr.delete.completed",
                resource={
                    "type": "data_delete_job",
                    "id": str(job_id),
                },
                payload={
                    "scope": scope,
                    "modules": modules_touched,
                },
            )
        else:
            emit_audit(
                org_id=org_id,
                event_type="gdpr.delete.failed",
                resource={
                    "type": "data_delete_job",
                    "id": str(job_id),
                },
                payload={
                    "scope": scope,
                    "failed_module": failed_module,
                    "error": last_error,
                    "modules_completed": modules_touched,
                },
            )
    finally:
        db.close()
