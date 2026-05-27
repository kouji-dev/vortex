"""S3 JSONL audit sink — append events to an S3-compatible archive.

One object per event keyed by ``YYYY/MM/DD/<event_id>.json`` (one JSON line
per file keeps keys immutable and lets retention DROP by prefix).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from ai_portal.audit.protocol import (
    AuditEventPayload,
    AuditFilter,
    SinkQueryUnsupported,
)


class S3JsonlAuditSink:
    name = "s3_jsonl"

    def __init__(self, blob_store, prefix: str = "audit") -> None:
        self._store = blob_store
        self._prefix = prefix.rstrip("/")

    async def write(self, event: AuditEventPayload) -> None:
        ts = event.created_at
        key = (
            f"{self._prefix}/{event.org_id}/"
            f"{ts.year:04d}/{ts.month:02d}/{ts.day:02d}/"
            f"{event.event_id}.json"
        )
        body = self._serialize(event).encode("utf-8")
        await self._store.put(key, body, "application/x-ndjson")

    async def query(self, f: AuditFilter) -> list[AuditEventPayload]:
        raise SinkQueryUnsupported("s3_jsonl is an archive sink; query via Postgres")

    @staticmethod
    def _serialize(event: AuditEventPayload) -> str:
        d = asdict(event)
        d["event_id"] = str(event.event_id)
        d["org_id"] = str(event.org_id)
        d["created_at"] = event.created_at.isoformat()
        return json.dumps(d, default=str)
