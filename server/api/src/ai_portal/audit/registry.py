"""Sink factory + per-org sink resolution.

Each org may activate any subset of bundled sinks via ``audit_retention_config.sink_configs``:
``[{"kind": "splunk_hec", "config": {"url": "...", "token": "..."}}, ...]``.

The Postgres sink is always implicitly active — it's the primary store.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_portal.audit.protocol import AuditSink

logger = logging.getLogger(__name__)


def build_sink(kind: str, config: dict[str, Any]) -> AuditSink:
    """Construct one sink instance from a (kind, config) pair."""
    if kind == "postgres":
        from ai_portal.audit.sinks.postgres import PostgresAuditSink  # noqa: PLC0415
        from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
        return PostgresAuditSink(SessionLocal)
    if kind == "s3_jsonl":
        from ai_portal.audit.sinks.s3_jsonl import S3JsonlAuditSink  # noqa: PLC0415
        return S3JsonlAuditSink(blob_store=config["blob_store"], prefix=config.get("prefix", "audit"))
    if kind == "splunk_hec":
        from ai_portal.audit.sinks.splunk_hec import SplunkHecAuditSink  # noqa: PLC0415
        return SplunkHecAuditSink(
            url=config["url"],
            token=config["token"],
            source=config.get("source", "ai-portal-audit"),
            timeout=config.get("timeout", 5.0),
        )
    if kind == "datadog_logs":
        from ai_portal.audit.sinks.datadog_logs import (
            DatadogLogsAuditSink,  # noqa: PLC0415
        )
        return DatadogLogsAuditSink(
            api_key=config["api_key"],
            site=config.get("site", "datadoghq.com"),
            service=config.get("service", "ai-portal"),
            timeout=config.get("timeout", 5.0),
        )
    if kind == "syslog":
        from ai_portal.audit.sinks.syslog import SyslogAuditSink  # noqa: PLC0415
        return SyslogAuditSink(
            host=config.get("host", "localhost"),
            port=config.get("port", 514),
            proto=config.get("proto", "udp"),
        )
    raise ValueError(f"unknown audit sink kind: {kind}")


def resolve_sinks_for_org(sink_configs: list[dict]) -> list[AuditSink]:
    """Build all sinks declared for one org. Skips any that fail to construct."""
    sinks: list[AuditSink] = []
    for entry in sink_configs or []:
        try:
            sinks.append(build_sink(entry["kind"], entry.get("config", {})))
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to build audit sink kind=%s: %s", entry.get("kind"), exc)
    return sinks
