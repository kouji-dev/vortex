"""Datadog Logs intake sink — POST to ``/api/v2/logs``.

Uses ``DD-API-KEY`` header. Each event becomes one log entry tagged with the
org id and event type for fast filtering in Datadog.
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


class DatadogLogsAuditSink:
    name = "datadog_logs"

    def __init__(
        self,
        api_key: str,
        site: str = "datadoghq.com",
        service: str = "ai-portal",
        timeout: float = 5.0,
    ) -> None:
        self._url = f"https://http-intake.logs.{site}/api/v2/logs"
        self._api_key = api_key
        self._service = service
        self._timeout = timeout

    async def write(self, event: AuditEventPayload) -> None:
        log_entry = {
            "ddsource": "ai-portal-audit",
            "ddtags": f"org:{event.org_id},event_type:{event.event_type}",
            "hostname": "ai-portal",
            "service": self._service,
            "message": json.dumps(self._event_dict(event), default=str),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._url,
                headers={"DD-API-KEY": self._api_key, "Content-Type": "application/json"},
                content=json.dumps([log_entry]),
            )
            resp.raise_for_status()

    async def query(self, f: AuditFilter) -> list[AuditEventPayload]:
        raise SinkQueryUnsupported("datadog_logs is a forward-only sink; query via Postgres")

    @staticmethod
    def _event_dict(event: AuditEventPayload) -> dict:
        d = asdict(event)
        d["event_id"] = str(event.event_id)
        d["org_id"] = str(event.org_id)
        d["created_at"] = event.created_at.isoformat()
        return d
