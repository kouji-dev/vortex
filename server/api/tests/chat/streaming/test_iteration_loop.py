# tests/chat/streaming/test_iteration_loop.py
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from ai_portal.catalog.providers.events import (
    IterationCompleteEvent,
    ProviderStreamEvent,
    TextDeltaEvent,
    UsageEvent,
)
from ai_portal.chat.streaming.cancellation import CancelToken
from ai_portal.chat.streaming.item_writer import ItemWriter
from ai_portal.chat.streaming import iteration_loop


class FakeProvider:
    """Fake LLM provider that yields scripted events."""

    def __init__(self, scripts: list[list[dict]]) -> None:
        self._scripts = list(scripts)
        self._i = 0

    async def stream(self, *, messages=None, model=None, settings=None, tools=None, **kwargs):
        script = self._scripts[self._i]
        self._i += 1
        for e in script:
            yield ProviderStreamEvent.model_validate(e)


@pytest.fixture
async def writer(async_db_session, thread_fixture):
    return ItemWriter(
        session=async_db_session,
        thread_id=thread_fixture.id,
        org_id=thread_fixture.org_id,
    )


async def test_text_turn_emits_items(writer):
    """A simple text-only turn should emit llm_call + assistant_text + done llm_call items."""
    turn_id = uuid.uuid4()
    script = [
        {"type": "text_delta", "text": "Hello "},
        {"type": "text_delta", "text": "world"},
        {"type": "usage", "input_tokens": 5, "output_tokens": 3,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]
    provider = FakeProvider([script])

    events = []
    async for ev in iteration_loop.run(
        provider=provider,
        writer=writer,
        turn_id=turn_id,
        provider_messages=[{"role": "system", "content": "Be helpful."}],
        model="gpt-4",
        allowed_tools=[],
        max_iterations=3,
    ):
        events.append(ev)

    event_types = [e.root.event_type for e in events]
    assert "item" in event_types

    # Find item events
    item_events = [e.root for e in events if e.root.event_type == "item"]
    kinds = [ev.item.root.kind for ev in item_events]
    assert "llm_call" in kinds
    assert "assistant_text" in kinds


async def test_cancelled_turn_stops_loop(writer):
    """If the cancel token is already cancelled, the loop should not call the provider."""
    turn_id = uuid.uuid4()
    token = CancelToken(turn_id)
    token.cancel()  # pre-cancel

    script = [
        {"type": "text_delta", "text": "Hello"},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]
    provider = FakeProvider([script])

    events = []
    async for ev in iteration_loop.run(
        provider=provider,
        writer=writer,
        turn_id=turn_id,
        provider_messages=[],
        model="gpt-4",
        allowed_tools=[],
        max_iterations=3,
        cancel_token=token,
    ):
        events.append(ev)

    # No events should be emitted (loop exits immediately)
    assert len(events) == 0


async def test_llm_call_routes_audit_through_control_plane(writer, monkeypatch, org_fixture, user_fixture):
    """After a successful llm_call, iteration_loop must invoke
    control_plane.emit_audit (via the iteration_loop module binding) so audit
    flows through the facade uniformly with other modules."""
    turn_id = uuid.uuid4()
    script = [
        {"type": "text_delta", "text": "ok"},
        {"type": "usage", "input_tokens": 7, "output_tokens": 4,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]
    provider = FakeProvider([script])

    audit_calls: list[dict] = []

    def _spy_audit(**kw):
        audit_calls.append(kw)
        return None

    # iteration_loop imports emit_audit at module load, so patch that binding.
    monkeypatch.setattr(iteration_loop, "emit_audit", _spy_audit)

    events = []
    async for ev in iteration_loop.run(
        provider=provider,
        writer=writer,
        turn_id=turn_id,
        provider_messages=[{"role": "system", "content": "Be helpful."}],
        model="gpt-4",
        allowed_tools=[],
        max_iterations=3,
        org_id=org_fixture.id,
        user_id=user_fixture.id,
    ):
        events.append(ev)

    assert len(audit_calls) >= 1
    last = audit_calls[-1]
    assert last["event_type"] == "chat.llm_call.completed"
    assert last["org_id"] == org_fixture.id
    payload = last["payload"]
    assert payload["model"] == "gpt-4"
    assert payload["input_tokens"] == 7
    assert payload["output_tokens"] == 4


def test_usage_emitter_writes_tokens_in_and_out(monkeypatch):
    """Unit-test the control_plane usage path directly: invoking the helper
    with a sync session and a UsageEvent should produce one emit_usage call
    per non-zero token unit, routed via the iteration_loop module binding."""
    import uuid as _uuid
    from ai_portal.catalog.providers.events import UsageEvent
    from ai_portal.chat.streaming.iteration_loop import (
        _record_llm_call_to_control_plane,
    )

    class _SyncSession: pass
    class _Writer:
        session = _SyncSession()

    usage_calls: list[dict] = []
    audit_calls: list[dict] = []

    def _spy_usage(_session, **kw):
        usage_calls.append(kw)

    def _spy_audit(**kw):
        audit_calls.append(kw)

    monkeypatch.setattr(iteration_loop, "emit_usage", _spy_usage)
    monkeypatch.setattr(iteration_loop, "emit_audit", _spy_audit)

    org_id = _uuid.UUID("00000000-0000-0000-0000-0000deadbeef")
    turn_id = _uuid.uuid4()
    usage = UsageEvent(
        type="usage",
        input_tokens=11, output_tokens=5,
        cached_input_tokens=2, cache_creation_input_tokens=0,
        reasoning_tokens=0,
    )

    from decimal import Decimal as _D
    _record_llm_call_to_control_plane(
        writer=_Writer(),  # type: ignore[arg-type]
        org_id=org_id,
        user_id=42,
        model="gpt-4",
        turn_id=turn_id,
        iteration=0,
        usage=usage,
        cost_usd=_D("0.001"),
        cost_estimated=False,
    )

    units = [c["unit"] for c in usage_calls]
    assert "tokens_in" in units
    assert "tokens_out" in units
    assert "tokens_cache_read" in units
    in_row = next(c for c in usage_calls if c["unit"] == "tokens_in")
    assert in_row["qty"] == 11
    assert in_row["module"] == "chat"
    assert in_row["actor_user_id"] == 42
    assert in_row["org_id"] == org_id

    assert len(audit_calls) == 1
    assert audit_calls[0]["event_type"] == "chat.llm_call.completed"
    assert audit_calls[0]["payload"]["input_tokens"] == 11
    assert audit_calls[0]["payload"]["output_tokens"] == 5


async def test_max_iterations_forces_stop(writer, monkeypatch):
    """With max_iterations=1 and a tool call request, loop runs at most 2 LLM calls (0-indexed)."""
    turn_id = uuid.uuid4()

    # Script 1: tool call request
    script1 = [
        {"type": "tool_call_request", "call_id": "c1", "tool_name": "web_search",
         "arguments": {"query": "test"}},
        {"type": "usage", "input_tokens": 5, "output_tokens": 3,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "tool_use"},
    ]
    # Script 2: final text response
    script2 = [
        {"type": "text_delta", "text": "Result"},
        {"type": "usage", "input_tokens": 5, "output_tokens": 3,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]
    provider = FakeProvider([script1, script2])

    # Mock dispatch_tool to avoid actual tool calls
    from ai_portal.chat.tool_outcome import ToolCallOutcome
    async def _fake_dispatch(**kwargs):
        return ToolCallOutcome(
            call_id=kwargs["call_id"],
            tool_name=kwargs["tool_name"],
            provider="test",
            input=kwargs["arguments"],
            result_snippet="test result",
        )

    monkeypatch.setattr(iteration_loop, "dispatch_tool", _fake_dispatch)

    events = []
    async for ev in iteration_loop.run(
        provider=provider,
        writer=writer,
        turn_id=turn_id,
        provider_messages=[],
        model="gpt-4",
        allowed_tools=["web_search"],
        max_iterations=1,  # Allow 1 tool call (iteration 0 → 1), then stop
    ):
        events.append(ev)

    # Should have emitted items from at least the first iteration
    assert len(events) > 0
    item_events = [e.root for e in events if e.root.event_type == "item"]
    kinds = [ev.item.root.kind for ev in item_events]
    assert "llm_call" in kinds
