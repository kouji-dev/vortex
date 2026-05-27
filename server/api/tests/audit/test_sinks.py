"""Audit sinks — unit tests for each bundled sink.

HTTP-backed sinks (Splunk HEC, Datadog Logs) are exercised with respx.
S3 sink uses an in-memory fake BlobStore.
Syslog is verified via a swapped handler that captures emitted records.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
import respx

from ai_portal.audit.protocol import AuditEventPayload, SinkQueryUnsupported
from ai_portal.audit.sinks.datadog_logs import DatadogLogsAuditSink
from ai_portal.audit.sinks.s3_jsonl import S3JsonlAuditSink
from ai_portal.audit.sinks.splunk_hec import SplunkHecAuditSink


def _event() -> AuditEventPayload:
    return AuditEventPayload(
        event_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        org_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        actor_user_id=42,
        actor_type="user",
        actor_json={"id": 42, "email": "a@b.com"},
        event_type="org.update",
        resource_type="org",
        resource_id="11111111-1111-1111-1111-111111111111",
        action="update",
        payload={"diff": {"name": ["old", "new"]}},
        metadata=None,
        request_id="req-123",
        ip_address="10.0.0.1",
        user_agent="ua",
        prev_hash="prev_abc",
        hash="hash_xyz",
        created_at=datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC),
    )


class _FakeBlobStore:
    """Captures put(...) calls; ignores the rest of the BlobStore protocol."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = (data, content_type)
        return f"s3://fake/{key}"


@pytest.mark.asyncio
async def test_s3_jsonl_writes_one_object_per_event() -> None:
    store = _FakeBlobStore()
    sink = S3JsonlAuditSink(blob_store=store, prefix="audit")
    ev = _event()
    await sink.write(ev)
    assert len(store.objects) == 1
    key = next(iter(store.objects))
    assert key.startswith(f"audit/{ev.org_id}/2026/05/28/")
    assert key.endswith(f"{ev.event_id}.json")
    body, ctype = store.objects[key]
    assert ctype == "application/x-ndjson"
    parsed = json.loads(body)
    assert parsed["event_type"] == "org.update"
    assert parsed["hash"] == "hash_xyz"
    assert parsed["prev_hash"] == "prev_abc"


@pytest.mark.asyncio
async def test_s3_jsonl_query_unsupported() -> None:
    from ai_portal.audit.protocol import AuditFilter
    store = _FakeBlobStore()
    sink = S3JsonlAuditSink(blob_store=store)
    with pytest.raises(SinkQueryUnsupported):
        await sink.query(AuditFilter())


@pytest.mark.asyncio
async def test_splunk_hec_posts_to_collector_endpoint() -> None:
    sink = SplunkHecAuditSink(url="https://splunk.example.com:8088", token="abc-token")
    with respx.mock(assert_all_called=True) as r:
        route = r.post("https://splunk.example.com:8088/services/collector/event").mock(
            return_value=httpx.Response(200, json={"text": "Success", "code": 0})
        )
        await sink.write(_event())
        req = route.calls.last.request
        assert req.headers["authorization"] == "Splunk abc-token"
        body = json.loads(req.content)
        assert body["sourcetype"] == "_json"
        assert body["event"]["event_type"] == "org.update"
        assert body["event"]["hash"] == "hash_xyz"


@pytest.mark.asyncio
async def test_splunk_hec_raises_on_5xx() -> None:
    sink = SplunkHecAuditSink(url="https://splunk.example.com:8088", token="abc-token")
    with respx.mock() as r:
        r.post("https://splunk.example.com:8088/services/collector/event").mock(
            return_value=httpx.Response(503, json={"error": "down"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await sink.write(_event())


@pytest.mark.asyncio
async def test_datadog_logs_posts_with_api_key_header() -> None:
    sink = DatadogLogsAuditSink(api_key="dd-key", site="datadoghq.com", service="ai-portal")
    with respx.mock(assert_all_called=True) as r:
        route = r.post("https://http-intake.logs.datadoghq.com/api/v2/logs").mock(
            return_value=httpx.Response(202)
        )
        await sink.write(_event())
        req = route.calls.last.request
        assert req.headers["dd-api-key"] == "dd-key"
        body = json.loads(req.content)
        assert isinstance(body, list) and len(body) == 1
        log = body[0]
        assert log["service"] == "ai-portal"
        assert "org:11111111-1111-1111-1111-111111111111" in log["ddtags"]
        assert "event_type:org.update" in log["ddtags"]
        inner = json.loads(log["message"])
        assert inner["hash"] == "hash_xyz"


@pytest.mark.asyncio
async def test_datadog_logs_raises_on_403() -> None:
    sink = DatadogLogsAuditSink(api_key="bad")
    with respx.mock() as r:
        r.post("https://http-intake.logs.datadoghq.com/api/v2/logs").mock(
            return_value=httpx.Response(403)
        )
        with pytest.raises(httpx.HTTPStatusError):
            await sink.write(_event())


@pytest.mark.asyncio
async def test_syslog_sink_emits_to_logger(monkeypatch) -> None:
    """SyslogAuditSink constructor opens a UDP socket; monkeypatch SysLogHandler."""
    captured: list[str] = []

    class _FakeHandler:
        level = 0
        def __init__(self, *a, **kw): ...
        def setLevel(self, lvl): self.level = lvl
        def setFormatter(self, fmt): ...
        def handle(self, record):
            captured.append(record.getMessage())
        def emit(self, record):
            captured.append(record.getMessage())
        def createLock(self): self.lock = None
        def acquire(self): ...
        def release(self): ...
        def flush(self): ...
        def close(self): ...
        def addFilter(self, *a, **kw): ...
        def removeFilter(self, *a, **kw): ...
        def filter(self, record): return True

    import ai_portal.audit.sinks.syslog as mod
    monkeypatch.setattr(mod, "SysLogHandler", _FakeHandler)

    sink = mod.SyslogAuditSink(host="localhost", port=514)
    await sink.write(_event())
    assert any("hash_xyz" in m for m in captured)


def test_splunk_hec_query_unsupported() -> None:
    import asyncio

    from ai_portal.audit.protocol import AuditFilter
    sink = SplunkHecAuditSink(url="https://x", token="t")
    with pytest.raises(SinkQueryUnsupported):
        asyncio.get_event_loop().run_until_complete(sink.query(AuditFilter())) if False else asyncio.run(sink.query(AuditFilter()))


def test_datadog_query_unsupported() -> None:
    import asyncio

    from ai_portal.audit.protocol import AuditFilter
    sink = DatadogLogsAuditSink(api_key="k")
    with pytest.raises(SinkQueryUnsupported):
        asyncio.run(sink.query(AuditFilter()))
