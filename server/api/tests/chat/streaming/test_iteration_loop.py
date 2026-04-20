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
