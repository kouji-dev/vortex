"""Splunk HEC audit sink — POST to ``/services/collector/event``.

Authentication is ``Authorization: Splunk <token>``. The payload uses Splunk's
``event`` wrapper plus ``time`` epoch seconds.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import httpx

from ai_portal.audit.protocol import (
    AuditEventPayload,
    AuditFilter,
    SinkQueryUnsupported,
)


class SplunkHecAuditSink:
    name = "splunk_hec"

    def __init__(self, url: str, token: str, source: str = "ai-portal-audit", timeout: float = 5.0) -> None:
        self._url = url.rstrip("/") + "/services/collector/event"
        self._token = token
        self._source = source
        self._timeout = timeout

    async def write(self, event: AuditEventPayload) -> None:
        body = {
            "time": event.created_at.timestamp(),
            "source": self._source,
            "sourcetype": "_json",
            "event": self._event_dict(event),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._url,
                headers={"Authorization": f"Splunk {self._token}"},
                content=json.dumps(body),
            )
            resp.raise_for_status()

    async def query(self, f: AuditFilter) -> list[AuditEventPayload]:
        raise SinkQueryUnsupported("splunk_hec is a forward-only sink; query via Postgres")

    @staticmethod
    def _event_dict(event: AuditEventPayload) -> dict:
        d = asdict(event)
        d["event_id"] = str(event.event_id)
        d["org_id"] = str(event.org_id)
        d["created_at"] = event.created_at.isoformat()
        return d
