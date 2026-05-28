"""Audit export — CSV / JSONL / S3 destination + streaming SIEM forwarder.

Three execution modes:

- ``download``: streaming response built by the router from a generator.
- ``s3``: enqueues a job; the worker writes a single object to BlobStore.
- ``siem``: enqueues a job; worker walks events and pushes through the
  org's configured external sink (Splunk HEC, Datadog Logs, etc.).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.audit.event_view import decrypt_actor, decrypt_payload
from ai_portal.audit.model import AuditEvent, AuditExportJob
from ai_portal.audit.protocol import AuditFilter

logger = logging.getLogger(__name__)


def event_to_dict(e: AuditEvent) -> dict:
    return {
        "id": e.id,
        "event_id": str(e.event_id),
        "org_id": str(e.org_id),
        "actor_user_id": e.actor_user_id,
        "actor_type": e.actor_type,
        "event_type": e.event_type,
        "resource_type": e.resource_type,
        "resource_id": e.resource_id,
        "action": e.action,
        "payload_json": decrypt_payload(e),
        "request_id": e.request_id,
        "ip_address": str(e.ip_address) if e.ip_address else None,
        "user_agent": e.user_agent,
        "prev_hash": e.prev_hash,
        "hash": e.hash,
        "created_at": e.created_at.isoformat(),
    }


def stream_jsonl(events: Iterable[AuditEvent]) -> Iterator[str]:
    for e in events:
        yield json.dumps(event_to_dict(e), default=str) + "\n"


def stream_csv(events: Iterable[AuditEvent]) -> Iterator[str]:
    cols = [
        "id", "event_id", "org_id", "actor_user_id", "event_type",
        "resource_type", "resource_id", "action", "prev_hash", "hash", "created_at",
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    yield buf.getvalue()
    for e in events:
        buf = io.StringIO()
        w = csv.writer(buf)
        d = event_to_dict(e)
        w.writerow([d[c] for c in cols])
        yield buf.getvalue()


def _filter_query(org_id: uuid.UUID, f: AuditFilter):
    q = select(AuditEvent).where(AuditEvent.org_id == org_id)
    if f.actor_user_id is not None:
        q = q.where(AuditEvent.actor_user_id == f.actor_user_id)
    if f.event_type:
        q = q.where(AuditEvent.event_type == f.event_type)
    if f.resource_type:
        q = q.where(AuditEvent.resource_type == f.resource_type)
    if f.resource_id:
        q = q.where(AuditEvent.resource_id == f.resource_id)
    if f.action:
        q = q.where(AuditEvent.action == f.action)
    if f.start:
        q = q.where(AuditEvent.created_at >= f.start)
    if f.end:
        q = q.where(AuditEvent.created_at < f.end)
    return q.order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())


def query_events(db: Session, org_id: uuid.UUID, f: AuditFilter) -> list[AuditEvent]:
    q = _filter_query(org_id, f).limit(f.limit).offset(f.offset)
    return list(db.scalars(q).all())


def count_events(db: Session, org_id: uuid.UUID, f: AuditFilter) -> int:
    from sqlalchemy import func  # noqa: PLC0415
    q = _filter_query(org_id, f)
    return db.scalar(select(func.count()).select_from(q.subquery())) or 0


def stream_for_export(db: Session, org_id: uuid.UUID, f: AuditFilter) -> list[AuditEvent]:
    """Full result-set, no limit. Caller is responsible for streaming."""
    q = _filter_query(org_id, f)
    return list(db.scalars(q).all())


# --- export job runners ---------------------------------------------------

def run_s3_export(
    db: Session,
    job: AuditExportJob,
    *,
    blob_store,
    bucket_prefix: str = "audit-exports",
) -> AuditExportJob:
    """Materialise the export into one BlobStore object. Mark the job done."""
    f = _filter_from_job(job)
    events = stream_for_export(db, job.org_id, f)
    if job.fmt == "csv":
        body = "".join(stream_csv(events))
        content_type = "text/csv"
        ext = "csv"
    else:
        body = "".join(stream_jsonl(events))
        content_type = "application/x-ndjson"
        ext = "jsonl"

    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    key = f"{bucket_prefix}/{job.org_id}/{ts}_{job.id}.{ext}"

    import asyncio  # noqa: PLC0415
    url = asyncio.run(blob_store.put(key, body.encode("utf-8"), content_type))

    job.blob_url = url
    job.status = "done"
    job.finished_at = datetime.now(tz=UTC)
    return job


def run_siem_export(
    db: Session,
    job: AuditExportJob,
    *,
    sink,
) -> AuditExportJob:
    """Walk the filtered events and push each through ``sink.write``."""
    from ai_portal.audit.protocol import AuditEventPayload  # noqa: PLC0415

    f = _filter_from_job(job)
    events = stream_for_export(db, job.org_id, f)

    import asyncio  # noqa: PLC0415

    async def _push_all() -> int:
        count = 0
        for e in events:
            payload = AuditEventPayload(
                event_id=e.event_id,
                org_id=e.org_id,
                actor_user_id=e.actor_user_id,
                actor_type=e.actor_type,
                actor_json=decrypt_actor(e),
                event_type=e.event_type,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                action=e.action,
                payload=decrypt_payload(e),
                metadata=decrypt_payload(e),
                request_id=e.request_id,
                ip_address=str(e.ip_address) if e.ip_address else None,
                user_agent=e.user_agent,
                prev_hash=e.prev_hash,
                hash=e.hash,
                created_at=e.created_at,
            )
            await sink.write(payload)
            count += 1
        return count

    pushed = asyncio.run(_push_all())
    job.status = "done"
    job.finished_at = datetime.now(tz=UTC)
    job.blob_url = f"siem://{sink.name}?count={pushed}"
    return job


def _filter_from_job(job: AuditExportJob) -> AuditFilter:
    fj = job.filter_json or {}
    return AuditFilter(
        org_id=job.org_id,
        actor_user_id=fj.get("actor_user_id"),
        event_type=fj.get("event_type"),
        resource_type=fj.get("resource_type"),
        resource_id=fj.get("resource_id"),
        action=fj.get("action"),
        start=_parse_dt(fj.get("start")),
        end=_parse_dt(fj.get("end")),
        limit=10_000_000,
        offset=0,
    )


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    return datetime.fromisoformat(s)
