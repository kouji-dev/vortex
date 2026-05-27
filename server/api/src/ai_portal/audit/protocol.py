"""AuditSink protocol — uniform contract across audit destinations.

Sinks are pluggable: ``postgres`` (default, always on), ``s3_jsonl``,
``splunk_hec``, ``datadog_logs``, ``syslog``. Multiple sinks may be active
concurrently for the same org (the service fans out).

``write`` must be idempotent on retry. ``query`` is optional — only the
primary store (Postgres) implements meaningful filtering; archive sinks
raise :class:`SinkQueryUnsupported`.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class SinkQueryUnsupported(NotImplementedError):
    """Raised by archive sinks (S3 JSONL, syslog) that don't support filtered reads."""


@dataclass
class AuditEventPayload:
    """Canonical event shape carried between service and sinks."""
    event_id: _uuid.UUID
    org_id: _uuid.UUID
    actor_user_id: int | None
    actor_type: str
    actor_json: dict | None
    event_type: str
    resource_type: str
    resource_id: str | None
    action: str
    payload: dict | None
    metadata: dict | None
    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    prev_hash: str | None
    hash: str
    created_at: datetime


@dataclass
class AuditFilter:
    """Search parameters. All fields optional; combined with AND."""
    org_id: _uuid.UUID | None = None
    actor_user_id: int | None = None
    event_type: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    action: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    limit: int = 100
    offset: int = 0


@runtime_checkable
class AuditSink(Protocol):
    """Uniform contract for audit destinations.

    ``name`` identifies the sink in retention config. ``write`` accepts a
    single event. Implementations are responsible for batching/buffering
    internally if their backend benefits from it.
    """

    name: str

    async def write(self, event: AuditEventPayload) -> None: ...

    async def query(self, f: AuditFilter) -> list[AuditEventPayload]: ...
