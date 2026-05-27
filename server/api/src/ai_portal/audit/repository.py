"""Audit repository — pure data access (no business logic, no chain math).

The repository deliberately exposes simple list/get helpers. Hash-chain
verification lives in :mod:`ai_portal.audit.chain`; the service owns the
write path with chain computation.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.audit.model import AuditEvent, AuditExportJob, AuditRetentionConfig


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- queries ---------------------------------------------------------

    def list_by_org(self, org_id: uuid.UUID, *, limit: int = 1000) -> list[AuditEvent]:
        q = (
            select(AuditEvent)
            .where(AuditEvent.org_id == org_id)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
            .limit(limit)
        )
        return list(self.db.scalars(q).all())

    def latest_hash(self, org_id: uuid.UUID) -> str | None:
        q = (
            select(AuditEvent.hash)
            .where(AuditEvent.org_id == org_id)
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
        return self.db.execute(q).scalar_one_or_none()

    # ---- retention config -----------------------------------------------

    def get_retention_config(self, org_id: uuid.UUID) -> AuditRetentionConfig | None:
        q = select(AuditRetentionConfig).where(AuditRetentionConfig.org_id == org_id)
        return self.db.execute(q).scalar_one_or_none()

    def upsert_retention_config(
        self,
        org_id: uuid.UUID,
        *,
        retention_days: int | None = None,
        sink_configs: list[dict] | None = None,
    ) -> AuditRetentionConfig:
        cfg = self.get_retention_config(org_id)
        if cfg is None:
            cfg = AuditRetentionConfig(
                org_id=org_id,
                retention_days=retention_days if retention_days is not None else 2555,
                sink_configs=sink_configs if sink_configs is not None else [],
            )
            self.db.add(cfg)
        else:
            if retention_days is not None:
                cfg.retention_days = retention_days
            if sink_configs is not None:
                cfg.sink_configs = sink_configs
        self.db.flush()
        return cfg

    # ---- export jobs -----------------------------------------------------

    def create_export_job(
        self,
        *,
        org_id: uuid.UUID,
        requested_by: int | None,
        fmt: str,
        destination: str,
        filter_json: dict | None,
    ) -> AuditExportJob:
        job = AuditExportJob(
            org_id=org_id,
            requested_by=requested_by,
            fmt=fmt,
            destination=destination,
            filter_json=filter_json,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def get_export_job(self, org_id: uuid.UUID, job_id: int) -> AuditExportJob | None:
        q = select(AuditExportJob).where(
            AuditExportJob.org_id == org_id,
            AuditExportJob.id == job_id,
        )
        return self.db.execute(q).scalar_one_or_none()
