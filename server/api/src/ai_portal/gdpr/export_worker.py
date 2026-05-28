"""Export worker — fans out registered exporters, builds zip, uploads, notifies.

Flow per job:

- mark row ``running``
- iterate :mod:`ai_portal.gdpr.registry` exporters; each returns a JSON-able
  dict, written to ``<module>.json`` inside an in-memory zip
- upload the zip via the passed :class:`BlobStore`
- presign the GET URL (default TTL 7 days)
- mark row ``succeeded`` + ``result_url`` + ``completed_at``
- send ``data_export_ready`` notification via the passed notifier when a
  recipient is provided

Failures mark the row ``failed`` and propagate nothing. The caller (queue
runner) is responsible for retry policy.
"""

from __future__ import annotations

import io
import json
import logging
import uuid as _uuid
import zipfile
from datetime import UTC, datetime
from typing import Protocol

from ai_portal.gdpr.registry import list_exporters

logger = logging.getLogger(__name__)


# 7 days. Long enough for the recipient to download the dump.
DEFAULT_PRESIGN_TTL_SECS = 7 * 24 * 3600


class _BlobLike(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def presign_get(self, key: str, expires_in: int) -> str: ...


class _NotifyLike(Protocol):
    async def send(
        self, *, channel: str, recipient: str, template_id: str, payload: dict
    ) -> None: ...


async def run_export_job(
    *,
    job_id: _uuid.UUID,
    blob_store: _BlobLike,
    notify: _NotifyLike | None = None,
    notify_recipient: str | None = None,
    notify_channel: str = "smtp",
    presign_ttl_secs: int = DEFAULT_PRESIGN_TTL_SECS,
) -> None:
    """Execute one queued export job."""
    from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415
    from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
    from ai_portal.gdpr.model import DataExportJob  # noqa: PLC0415

    db = SessionLocal()
    try:
        with bypass_rls(db):
            row = db.get(DataExportJob, job_id)
            if row is None:
                logger.warning("export job %s not found", job_id)
                return
            org_id = row.org_id
            row.status = "running"
            db.commit()

        try:
            zip_bytes = await _build_zip(org_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("export build failed: %s", exc)
            with bypass_rls(db):
                row = db.get(DataExportJob, job_id)
                if row is not None:
                    row.status = "failed"
                    row.completed_at = datetime.now(tz=UTC)
                    db.commit()
            return

        key = f"gdpr/exports/{org_id}/{job_id}.zip"
        await blob_store.put(key, zip_bytes, "application/zip")
        url = await blob_store.presign_get(key, presign_ttl_secs)

        with bypass_rls(db):
            row = db.get(DataExportJob, job_id)
            if row is not None:
                row.status = "succeeded"
                row.result_url = url
                row.completed_at = datetime.now(tz=UTC)
                db.commit()

        if notify is not None and notify_recipient:
            try:
                await notify.send(
                    channel=notify_channel,
                    recipient=notify_recipient,
                    template_id="data_export_ready",
                    payload={"url": url, "job_id": str(job_id)},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("export notify failed: %s", exc)
    finally:
        db.close()


async def _build_zip(org_id: _uuid.UUID) -> bytes:
    """Run every registered exporter and pack their dicts as JSON into a zip."""
    buf = io.BytesIO()
    exporters = list_exporters()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for module_name, fn in exporters.items():
            try:
                payload = await fn(org_id)
            except Exception as exc:  # noqa: BLE001
                # One module failing must not poison the rest. Record an
                # error file inside the zip so the recipient sees the gap.
                logger.exception("exporter for %s raised: %s", module_name, exc)
                payload = {"error": str(exc)}
            zf.writestr(
                f"{module_name}.json",
                json.dumps(payload, default=str, sort_keys=True, indent=2),
            )
        # Always include a manifest so empty-export zips remain inspectable.
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "org_id": str(org_id),
                    "modules": sorted(exporters.keys()),
                    "generated_at": datetime.now(tz=UTC).isoformat(),
                },
                sort_keys=True,
                indent=2,
            ),
        )
    return buf.getvalue()
