from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ai_portal.core.db.session import SessionLocal
from ai_portal.knowledge_base.model import CONNECTOR_KINDS, ConnectorSyncJob, KnowledgeBaseConnector

logger = logging.getLogger(__name__)

_REMOTE_KINDS = frozenset(k for k in CONNECTOR_KINDS if k != "files")


def run_connector_sync_job(job_id: int) -> None:
    """Execute a connector sync job (background thread / worker)."""
    db: Session = SessionLocal()
    job: ConnectorSyncJob | None = None
    try:
        job = db.get(ConnectorSyncJob, job_id)
        if job is None:
            return
        if job.status != "queued":
            return

        now = datetime.now(UTC)
        job.status = "running"
        job.started_at = now
        db.commit()

        connector = db.get(KnowledgeBaseConnector, job.connector_id)
        if connector is None or not connector.enabled:
            job.status = "failed"
            job.error_message = "Connector missing or disabled"
            job.finished_at = datetime.now(UTC)
            db.commit()
            return

        meta: dict = {"connector_kind": connector.kind}

        if connector.kind == "files":
            meta["message"] = (
                "Uploads are ingested when files are posted; no remote sync step."
            )
            job.status = "succeeded"
            job.meta = meta
        elif connector.kind in _REMOTE_KINDS:
            # Orchestration hook: replace with real GitHub/GitLab/Confluence/S3 pulls.
            meta["implementation"] = "pending"
            meta["message"] = (
                f"{connector.kind} sync is not implemented yet; job pipeline is ready."
            )
            job.status = "succeeded"
            job.meta = meta
        else:
            job.status = "failed"
            job.error_message = f"Unknown connector kind: {connector.kind}"
            job.meta = meta

        job.finished_at = datetime.now(UTC)
        db.commit()
    except Exception:
        logger.exception("connector_sync_job_failed", extra={"job_id": job_id})
        if job is None:
            job = db.get(ConnectorSyncJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_message = "Internal error during sync"
            job.finished_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()
