"""Unit tests for ``EventWriter`` — broadcast + batching, no DB."""

from __future__ import annotations

import asyncio

import pytest

from ai_portal.workers.events.writer import (
    EventRecord,
    EventWriter,
    get_writer,
    set_writer,
    subscription,
)
from ai_portal.workers.types import EventKind


@pytest.mark.asyncio
async def test_emit_broadcasts_to_subscribers() -> None:
    w = EventWriter()
    received: list[EventRecord] = []

    async def cb(rec: EventRecord) -> None:
        received.append(rec)

    w.subscribe("run-1", cb)
    rec = await w.emit("run-1", EventKind.agent_thought, {"text": "hi"})
    assert len(received) == 1
    assert received[0].run_id == "run-1"
    assert received[0].kind == "agent_thought"
    assert received[0].payload == {"text": "hi"}
    assert received[0].id == rec.id


@pytest.mark.asyncio
async def test_emit_ignores_subscribers_for_other_runs() -> None:
    w = EventWriter()
    a: list[EventRecord] = []
    b: list[EventRecord] = []

    async def cb_a(rec: EventRecord) -> None:
        a.append(rec)

    async def cb_b(rec: EventRecord) -> None:
        b.append(rec)

    w.subscribe("run-A", cb_a)
    w.subscribe("run-B", cb_b)
    await w.emit("run-A", EventKind.tool_call, {"tool": "shell"})
    assert len(a) == 1 and len(b) == 0


@pytest.mark.asyncio
async def test_unsubscribe_stops_receiving() -> None:
    w = EventWriter()
    received: list[EventRecord] = []

    async def cb(rec: EventRecord) -> None:
        received.append(rec)

    w.subscribe("r", cb)
    await w.emit("r", EventKind.agent_thought, {})
    w.unsubscribe("r", cb)
    await w.emit("r", EventKind.agent_thought, {})
    assert len(received) == 1


@pytest.mark.asyncio
async def test_failing_subscriber_does_not_block_others() -> None:
    w = EventWriter()
    good: list[EventRecord] = []

    async def good_cb(rec: EventRecord) -> None:
        good.append(rec)

    async def bad_cb(rec: EventRecord) -> None:
        raise RuntimeError("boom")

    w.subscribe("r", bad_cb)
    w.subscribe("r", good_cb)
    await w.emit("r", EventKind.error, {})
    assert len(good) == 1


@pytest.mark.asyncio
async def test_kind_accepts_str_or_enum() -> None:
    w = EventWriter()
    received: list[EventRecord] = []

    async def cb(rec: EventRecord) -> None:
        received.append(rec)

    w.subscribe("r", cb)
    await w.emit("r", "custom_kind", {})
    await w.emit("r", EventKind.phase_changed, {})
    kinds = [r.kind for r in received]
    assert kinds == ["custom_kind", "phase_changed"]


@pytest.mark.asyncio
async def test_subscription_context_manager() -> None:
    w = EventWriter()
    received: list[EventRecord] = []

    async def cb(rec: EventRecord) -> None:
        received.append(rec)

    async with subscription(w, "r", cb):
        await w.emit("r", EventKind.agent_thought, {})
        assert w.subscriber_count("r") == 1
    # outside the context: unsubscribed
    assert w.subscriber_count("r") == 0
    await w.emit("r", EventKind.agent_thought, {})
    assert len(received) == 1


@pytest.mark.asyncio
async def test_singleton_get_set() -> None:
    w = EventWriter()
    set_writer(w)
    try:
        assert get_writer() is w
    finally:
        set_writer(None)


@pytest.mark.asyncio
async def test_emit_returns_record_with_id_run_kind_payload() -> None:
    w = EventWriter()
    rec = await w.emit("r-1", EventKind.cost_update, {"cents": 42})
    assert rec.run_id == "r-1"
    assert rec.kind == "cost_update"
    assert rec.payload == {"cents": 42}
    assert isinstance(rec.id, str) and len(rec.id) > 0


@pytest.mark.asyncio
async def test_drain_loop_lifecycle_no_session_factory() -> None:
    w = EventWriter(session_factory=None, flush_interval_sec=0.01)
    await w.start()
    # emit several events; drain loop should silently consume them
    for _ in range(5):
        await w.emit("r", EventKind.shell_output, {"chunk": "x"})
    await asyncio.sleep(0.05)
    await w.stop()


@pytest.mark.asyncio
async def test_subscriber_count_tracks_subs() -> None:
    w = EventWriter()

    async def cb1(_: EventRecord) -> None: ...
    async def cb2(_: EventRecord) -> None: ...

    assert w.subscriber_count("r") == 0
    w.subscribe("r", cb1)
    w.subscribe("r", cb2)
    assert w.subscriber_count("r") == 2
    w.unsubscribe("r", cb1)
    assert w.subscriber_count("r") == 1
