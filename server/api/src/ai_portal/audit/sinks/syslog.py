"""Syslog audit sink — RFC 5424 over UDP/TCP.

Uses the stdlib :class:`logging.handlers.SysLogHandler`. The actual blocking
socket I/O is run in a thread to avoid stalling the event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from logging.handlers import SysLogHandler

from ai_portal.audit.protocol import (
    AuditEventPayload,
    AuditFilter,
    SinkQueryUnsupported,
)


class SyslogAuditSink:
    name = "syslog"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 514,
        facility: int = SysLogHandler.LOG_LOCAL0,
        proto: str = "udp",
    ) -> None:
        socktype = None
        if proto.lower() == "tcp":
            import socket as _sock
            socktype = _sock.SOCK_STREAM
        self._handler = SysLogHandler(address=(host, port), facility=facility, socktype=socktype)
        self._logger = logging.getLogger(f"ai_portal.audit.syslog.{host}.{port}")
        # Avoid duplicate handlers if the sink is constructed multiple times.
        if not any(isinstance(h, SysLogHandler) for h in self._logger.handlers):
            self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

    async def write(self, event: AuditEventPayload) -> None:
        msg = json.dumps(self._event_dict(event), default=str)
        await asyncio.to_thread(self._logger.info, msg)

    async def query(self, f: AuditFilter) -> list[AuditEventPayload]:
        raise SinkQueryUnsupported("syslog is a forward-only sink; query via Postgres")

    @staticmethod
    def _event_dict(event: AuditEventPayload) -> dict:
        d = asdict(event)
        d["event_id"] = str(event.event_id)
        d["org_id"] = str(event.org_id)
        d["created_at"] = event.created_at.isoformat()
        return d
