"""Audit hash chain — unit tests for the pure compute/verify functions.

These don't need Postgres: they exercise :mod:`ai_portal.audit.chain` directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ai_portal.audit.chain import compute_hash, verify_chain


@dataclass
class _FakeRow:
    event_id: uuid.UUID
    org_id: uuid.UUID
    event_type: str
    action: str
    resource_type: str
    resource_id: str | None
    payload_json: dict | None
    created_at: datetime
    prev_hash: str | None
    hash: str


def _make_chain(n: int = 3, *, org_id: uuid.UUID | None = None) -> list[_FakeRow]:
    org = org_id or uuid.uuid4()
    rows: list[_FakeRow] = []
    prev = None
    base = datetime(2026, 5, 28, tzinfo=UTC)
    for i in range(n):
        eid = uuid.uuid4()
        ts = base + timedelta(seconds=i)
        payload = {"i": i}
        h = compute_hash(
            event_id=eid,
            org_id=org,
            event_type=f"test.event.{i}",
            action="create",
            resource_type="test",
            resource_id=str(i),
            payload=payload,
            created_at=ts,
            prev_hash=prev,
        )
        rows.append(_FakeRow(
            event_id=eid,
            org_id=org,
            event_type=f"test.event.{i}",
            action="create",
            resource_type="test",
            resource_id=str(i),
            payload_json=payload,
            created_at=ts,
            prev_hash=prev,
            hash=h,
        ))
        prev = h
    return rows


def test_compute_hash_deterministic() -> None:
    eid = uuid.uuid4()
    org = uuid.uuid4()
    ts = datetime(2026, 5, 28, tzinfo=UTC)
    h1 = compute_hash(
        event_id=eid, org_id=org, event_type="x", action="a",
        resource_type="r", resource_id="1", payload={"k": "v"},
        created_at=ts, prev_hash=None,
    )
    h2 = compute_hash(
        event_id=eid, org_id=org, event_type="x", action="a",
        resource_type="r", resource_id="1", payload={"k": "v"},
        created_at=ts, prev_hash=None,
    )
    assert h1 == h2
    assert len(h1) == 64


def test_compute_hash_changes_with_payload() -> None:
    eid = uuid.uuid4()
    org = uuid.uuid4()
    ts = datetime(2026, 5, 28, tzinfo=UTC)
    base = dict(
        event_id=eid, org_id=org, event_type="x", action="a",
        resource_type="r", resource_id="1", created_at=ts, prev_hash=None,
    )
    h1 = compute_hash(payload={"k": "v1"}, **base)
    h2 = compute_hash(payload={"k": "v2"}, **base)
    assert h1 != h2


def test_compute_hash_chains_via_prev_hash() -> None:
    eid = uuid.uuid4()
    org = uuid.uuid4()
    ts = datetime(2026, 5, 28, tzinfo=UTC)
    base = dict(
        event_id=eid, org_id=org, event_type="x", action="a",
        resource_type="r", resource_id="1", payload={"k": "v"},
        created_at=ts,
    )
    h_no_prev = compute_hash(prev_hash=None, **base)
    h_with_prev = compute_hash(prev_hash="abc", **base)
    assert h_no_prev != h_with_prev


def test_verify_chain_intact_returns_ok() -> None:
    rows = _make_chain(5)
    ok, bad = verify_chain(rows)
    assert ok is True
    assert bad is None


def test_verify_chain_detects_payload_tamper() -> None:
    rows = _make_chain(5)
    # Tamper with event 2's payload after the fact (hash is now stale).
    rows[2].payload_json = {"i": 999}
    ok, bad = verify_chain(rows)
    assert ok is False
    assert bad == 2


def test_verify_chain_detects_prev_hash_swap() -> None:
    rows = _make_chain(4)
    rows[2].prev_hash = "deadbeef"
    ok, bad = verify_chain(rows)
    assert ok is False
    assert bad == 2


def test_verify_chain_detects_hash_tamper() -> None:
    rows = _make_chain(4)
    rows[1].hash = "0" * 64
    ok, bad = verify_chain(rows)
    assert ok is False
    assert bad == 1


def test_verify_chain_empty_is_ok() -> None:
    ok, bad = verify_chain([])
    assert ok is True
    assert bad is None
