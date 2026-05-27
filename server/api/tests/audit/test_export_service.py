"""Audit export service — pure-fn tests for CSV/JSONL streaming + S3/SIEM runners."""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from ai_portal.audit.export_service import (
    event_to_dict,
    run_s3_export,
    run_siem_export,
    stream_csv,
    stream_jsonl,
)


def _fake_event(i: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=i + 1,
        event_id=uuid.uuid4(),
        org_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        actor_user_id=42,
        actor_type="user",
        actor_json=None,
        event_type=f"test.event.{i}",
        resource_type="thing",
        resource_id=str(i),
        action="create",
        payload_json={"i": i},
        metadata_={},
        request_id=None,
        ip_address=None,
        user_agent=None,
        prev_hash=None if i == 0 else f"prev_{i}",
        hash=f"hash_{i}",
        created_at=datetime(2026, 5, 28, 12, i, 0, tzinfo=UTC),
    )


def test_event_to_dict_includes_chain_fields() -> None:
    d = event_to_dict(_fake_event(1))
    assert d["hash"] == "hash_1"
    assert d["prev_hash"] == "prev_1"
    assert d["event_type"] == "test.event.1"
    assert "created_at" in d


def test_stream_jsonl_one_line_per_event() -> None:
    events = [_fake_event(i) for i in range(3)]
    out = "".join(stream_jsonl(events))
    lines = [ln for ln in out.split("\n") if ln]
    assert len(lines) == 3
    parsed = [json.loads(ln) for ln in lines]
    assert [p["event_type"] for p in parsed] == [
        "test.event.0", "test.event.1", "test.event.2",
    ]


def test_stream_csv_has_header_then_rows() -> None:
    events = [_fake_event(i) for i in range(2)]
    out = "".join(stream_csv(events))
    reader = csv.reader(io.StringIO(out))
    rows = list(reader)
    assert rows[0][0] == "id"
    assert rows[0][-1] == "created_at"
    assert len(rows) == 1 + 2


class _CaptureBlob:
    def __init__(self) -> None:
        self.put_calls: list[tuple[str, bytes, str]] = []

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        self.put_calls.append((key, data, content_type))
        return f"s3://test/{key}"


def test_run_s3_export_writes_one_object_jsonl() -> None:
    events = [_fake_event(i) for i in range(2)]
    db = SimpleNamespace(scalars=lambda *a, **kw: SimpleNamespace(all=lambda: events))
    job = SimpleNamespace(
        id=99,
        org_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        fmt="jsonl",
        destination="s3",
        filter_json=None,
        status="pending",
        blob_url=None,
        finished_at=None,
    )
    blob = _CaptureBlob()
    out = run_s3_export(db, job, blob_store=blob, bucket_prefix="audits")
    assert out.status == "done"
    assert out.blob_url.startswith("s3://test/audits/")
    assert out.blob_url.endswith(".jsonl")
    assert len(blob.put_calls) == 1
    body = blob.put_calls[0][1].decode()
    assert body.count("\n") == 2


def test_run_s3_export_csv_format() -> None:
    events = [_fake_event(i) for i in range(2)]
    db = SimpleNamespace(scalars=lambda *a, **kw: SimpleNamespace(all=lambda: events))
    job = SimpleNamespace(
        id=100,
        org_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        fmt="csv",
        destination="s3",
        filter_json=None,
        status="pending",
        blob_url=None,
        finished_at=None,
    )
    blob = _CaptureBlob()
    out = run_s3_export(db, job, blob_store=blob)
    assert out.blob_url.endswith(".csv")
    body = blob.put_calls[0][1].decode()
    assert body.splitlines()[0].startswith("id,event_id,org_id")


def test_run_siem_export_walks_all_events() -> None:
    events = [_fake_event(i) for i in range(3)]
    db = SimpleNamespace(scalars=lambda *a, **kw: SimpleNamespace(all=lambda: events))
    job = SimpleNamespace(
        id=200,
        org_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        fmt="jsonl",
        destination="siem",
        filter_json=None,
        status="pending",
        blob_url=None,
        finished_at=None,
    )

    pushed: list = []

    class _Sink:
        name = "fake_siem"
        async def write(self, ev): pushed.append(ev)

    out = run_siem_export(db, job, sink=_Sink())
    assert out.status == "done"
    assert out.blob_url == "siem://fake_siem?count=3"
    assert len(pushed) == 3
