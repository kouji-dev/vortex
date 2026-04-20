"""Tests that AnthropicNativeChatProvider.stream yields typed ProviderStreamEvent."""

import pytest
from unittest.mock import MagicMock, patch

from ai_portal.catalog.providers.anthropic_native import AnthropicNativeChatProvider
from ai_portal.catalog.providers.events import (
    TextDeltaEvent,
    ToolCallRequestEvent,
    UsageEvent,
    IterationCompleteEvent,
    ProviderStreamEvent,
)


def _make_event(class_name: str, **attrs):
    """Create a fake SDK event where type(event).__name__ == class_name."""
    # We create a new class dynamically so type(event).__name__ returns class_name.
    cls = type(class_name, (), {})
    obj = cls()
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _ns(**kwargs):
    """Build a simple namespace object for nested attributes."""
    ns = MagicMock()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _make_events():
    """Build minimal SDK-style events covering text_delta + usage."""
    # RawMessageStartEvent
    usage_start = _ns(input_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    msg_start = _make_event("RawMessageStartEvent", message=_ns(usage=usage_start))

    # RawContentBlockStartEvent — text block
    cb_start = _make_event(
        "RawContentBlockStartEvent",
        content_block=_ns(type="text"),
    )

    # RawContentBlockDeltaEvent — text_delta
    cb_delta = _make_event(
        "RawContentBlockDeltaEvent",
        delta=_ns(type="text_delta", text="hi"),
    )

    # RawContentBlockStopEvent
    cb_stop = _make_event("RawContentBlockStopEvent")

    # RawMessageDeltaEvent — carries output token count
    msg_delta = _make_event(
        "RawMessageDeltaEvent",
        usage=_ns(output_tokens=20),
    )

    # RawMessageStopEvent
    msg_stop = _make_event("RawMessageStopEvent")

    return [msg_start, cb_start, cb_delta, cb_stop, msg_delta, msg_stop]


async def test_stream_yields_typed_events():
    """stream() yields TextDeltaEvent, UsageEvent, IterationCompleteEvent."""
    sdk_events = _make_events()

    # Patch the Anthropic sync client's messages.stream context manager.
    fake_stream_ctx = MagicMock()
    fake_stream_ctx.__enter__ = MagicMock(return_value=iter(sdk_events))
    fake_stream_ctx.__exit__ = MagicMock(return_value=False)

    fake_messages = MagicMock()
    fake_messages.stream = MagicMock(return_value=fake_stream_ctx)

    fake_client = MagicMock()
    fake_client.messages = fake_messages

    settings = MagicMock()
    settings.anthropic_api_key = "sk-fake"
    settings.chat_default_api_model = "claude-sonnet-4-6"

    with patch("anthropic.Anthropic", return_value=fake_client):
        prov = AnthropicNativeChatProvider(settings)
        collected = []
        async for ev in prov.stream(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-6",
            settings={},
            tools=None,
        ):
            collected.append(ev.root)

    assert any(isinstance(e, TextDeltaEvent) and e.text == "hi" for e in collected), (
        f"No TextDeltaEvent with text='hi' in {collected}"
    )
    assert any(isinstance(e, UsageEvent) and e.output_tokens == 20 for e in collected), (
        f"No UsageEvent with output_tokens=20 in {collected}"
    )
    assert any(isinstance(e, IterationCompleteEvent) for e in collected), (
        f"No IterationCompleteEvent in {collected}"
    )
    assert any(isinstance(e, IterationCompleteEvent) and e.stop_reason == "end_turn" for e in collected), (
        f"No IterationCompleteEvent with stop_reason='end_turn' in {collected}"
    )


async def test_stream_tool_call_accumulation():
    """Verifies tool args are accumulated across input_json_delta events before emitting ToolCallRequestEvent."""
    # Simulate: content_block_start(tool_use) + two input_json_delta chunks + content_block_stop
    sdk_events = [
        _make_event(
            "RawContentBlockStartEvent",
            content_block=_ns(type="tool_use", id="call_1", name="web_search"),
        ),
        _make_event(
            "RawContentBlockDeltaEvent",
            delta=_ns(type="input_json_delta", partial_json='{"q":'),
        ),
        _make_event(
            "RawContentBlockDeltaEvent",
            delta=_ns(type="input_json_delta", partial_json='"hello"}'),
        ),
        _make_event("RawContentBlockStopEvent"),
        _make_event(
            "RawMessageDeltaEvent",
            usage=_ns(output_tokens=10),
            delta=_ns(stop_reason="tool_use"),
        ),
        _make_event("RawMessageStopEvent"),
    ]

    # Patch the Anthropic sync client's messages.stream context manager.
    fake_stream_ctx = MagicMock()
    fake_stream_ctx.__enter__ = MagicMock(return_value=iter(sdk_events))
    fake_stream_ctx.__exit__ = MagicMock(return_value=False)

    fake_messages = MagicMock()
    fake_messages.stream = MagicMock(return_value=fake_stream_ctx)

    fake_client = MagicMock()
    fake_client.messages = fake_messages

    settings = MagicMock()
    settings.anthropic_api_key = "sk-fake"
    settings.chat_default_api_model = "claude-sonnet-4-6"

    with patch("anthropic.Anthropic", return_value=fake_client):
        prov = AnthropicNativeChatProvider(settings)
        collected = []
        async for ev in prov.stream(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-6",
            settings={},
            tools=None,
        ):
            collected.append(ev.root)

    # The two partial JSON fragments should be joined and parsed into a ToolCallRequestEvent
    tool_events = [e for e in collected if isinstance(e, ToolCallRequestEvent)]
    assert len(tool_events) == 1, f"Expected 1 ToolCallRequestEvent, got {len(tool_events)}"
    assert tool_events[0].call_id == "call_1"
    assert tool_events[0].tool_name == "web_search"
    assert tool_events[0].arguments == {"q": "hello"}

    # stop_reason should be "tool_use" from message_delta
    assert any(isinstance(e, IterationCompleteEvent) and e.stop_reason == "tool_use" for e in collected), (
        f"No IterationCompleteEvent with stop_reason='tool_use' in {collected}"
    )
