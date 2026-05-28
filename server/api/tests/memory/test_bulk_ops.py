"""Phase Polish-T5 — bulk pin / tag operations."""
from __future__ import annotations

import inspect
import uuid

import pytest

from ai_portal.memory.schemas import BulkPinRequest, BulkTagRequest
from ai_portal.memory.service import MemoryService


def test_bulk_pin_request_requires_ids() -> None:
    with pytest.raises(Exception):
        BulkPinRequest(ids=[], pinned=True)


def test_bulk_pin_request_round_trip() -> None:
    body = BulkPinRequest(ids=[uuid.uuid4()], pinned=False)
    assert body.pinned is False
    assert len(body.ids) == 1


def test_bulk_tag_request_defaults_empty_lists() -> None:
    body = BulkTagRequest(ids=[uuid.uuid4()])
    assert body.add == []
    assert body.remove == []


def test_bulk_tag_request_accepts_both() -> None:
    body = BulkTagRequest(ids=[uuid.uuid4()], add=["a"], remove=["b"])
    assert body.add == ["a"]
    assert body.remove == ["b"]


def test_service_has_bulk_pin() -> None:
    assert inspect.iscoroutinefunction(MemoryService.bulk_pin)


def test_service_has_bulk_tag() -> None:
    assert inspect.iscoroutinefunction(MemoryService.bulk_tag)


def test_router_bulk_endpoints_registered() -> None:
    from ai_portal.memory.v1_router import router

    paths = {r.path for r in router.routes}
    assert "/v1/memories/bulk-pin" in paths
    assert "/v1/memories/bulk-tag" in paths


def test_bulk_pin_signature() -> None:
    sig = inspect.signature(MemoryService.bulk_pin)
    assert {"org_id", "actor_user_id", "ids", "pinned"} <= set(sig.parameters)


def test_bulk_tag_signature() -> None:
    sig = inspect.signature(MemoryService.bulk_tag)
    assert {"org_id", "actor_user_id", "ids", "add", "remove"} <= set(sig.parameters)


@pytest.mark.asyncio
async def test_bulk_pin_no_ids_short_circuits() -> None:
    # bulk_pin with empty ids returns 0 without touching DB
    class _S:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, *_a, **_k):
            self.calls += 1
            raise AssertionError("should not execute")

        async def flush(self):
            self.calls += 1

    svc = MemoryService.__new__(MemoryService)
    svc.s = _S()
    out = await MemoryService.bulk_pin(
        svc, org_id=uuid.uuid4(), actor_user_id=1, ids=[], pinned=True
    )
    assert out == 0
    assert svc.s.calls == 0


@pytest.mark.asyncio
async def test_bulk_tag_no_changes_short_circuits() -> None:
    class _S:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, *_a, **_k):
            self.calls += 1
            raise AssertionError("should not execute")

        async def flush(self):
            self.calls += 1

    svc = MemoryService.__new__(MemoryService)
    svc.s = _S()
    out = await MemoryService.bulk_tag(
        svc, org_id=uuid.uuid4(), actor_user_id=1, ids=[uuid.uuid4()], add=[], remove=[]
    )
    assert out == 0
    assert svc.s.calls == 0
