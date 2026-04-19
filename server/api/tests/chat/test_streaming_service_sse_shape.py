"""Tests for SSE event shapes emitted by _stream_loop.

Verifies:
1. No thinking wrapper events are emitted
2. Memory item is emitted flat (item_start + item_done with kind='memory')
3. web_search tool emits kind='web_search' (not kind='tool_call')
4. stream_items are persisted in extra.stream_items on the ChatMessage
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ai_portal.chat.streaming_service import _stream_loop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sse_events(sse_output: list[str]) -> list[dict]:
    """Parse a list of SSE strings into dicts."""
    events = []
    for chunk in sse_output:
        for line in chunk.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                payload = line[len("data: "):]
                events.append(json.loads(payload))
    return events


def _make_stream_loop_kwargs(
    *,
    active_memory_count: int = 0,
    tools: list | None = None,
    provider_pieces: list | None = None,
    db: MagicMock | None = None,
    conv: MagicMock | None = None,
) -> dict:
    """Build kwargs for _stream_loop with sensible mocks."""
    if db is None:
        db = MagicMock()
    if conv is None:
        conv = MagicMock()
        conv.id = 1

    # Default: provider returns a single text delta then stops
    if provider_pieces is None:
        provider_pieces = [{"type": "delta", "text": "hello"}]

    settings = MagicMock()
    settings.conversation_base_window_size = 10
    settings.conversation_summary_interval = 5
    settings.rag_max_tool_iterations = 5

    # tail_message_id returns a stable id
    tail_message_id = MagicMock(return_value=42)

    return dict(
        db=db,
        conv=conv,
        user=MagicMock(),
        user_content="test",
        llm_messages=[{"role": "user", "content": "test"}],
        tools=tools or [],
        use_model=None,
        settings=settings,
        active_memory_count=active_memory_count,
        kb_ids=[],
        tail_message_id=tail_message_id,
        max_iterations=5,
    )


def _run_stream_loop(**kwargs) -> list[dict]:
    """Run _stream_loop and return parsed SSE events."""
    with (
        patch("ai_portal.chat.streaming_service.LlmProviderFactory.create") as mock_provider_factory,
        patch("ai_portal.chat.streaming_service.repo.count_messages_in_conversation", return_value=3),
        patch("ai_portal.chat.streaming_service.should_summarize", return_value=False),
        patch("ai_portal.chat.streaming_service.threading.Thread"),
    ):
        provider = MagicMock()
        mock_provider_factory.return_value = provider
        provider.stream_deltas_with_tools.return_value = iter(
            kwargs.pop("_provider_pieces", [{"type": "delta", "text": "hi"}])
        )

        raw = list(_stream_loop(**kwargs))
    return _parse_sse_events(raw)


# ---------------------------------------------------------------------------
# Test 1: No thinking events emitted
# ---------------------------------------------------------------------------

def test_no_thinking_events_in_sse():
    """Stream with active_memory_count=0 and no tools should never emit kind='thinking'."""
    kwargs = _make_stream_loop_kwargs(active_memory_count=0, tools=[])
    events = _run_stream_loop(**kwargs, _provider_pieces=[{"type": "delta", "text": "hello"}])

    thinking_events = [
        e for e in events
        if e.get("item", {}).get("kind") == "thinking"
    ]
    assert thinking_events == [], f"Found unexpected thinking events: {thinking_events}"


# ---------------------------------------------------------------------------
# Test 2: Memory item emitted flat (no thinking wrapper)
# ---------------------------------------------------------------------------

def test_memory_item_emitted_flat():
    """Stream with active_memory_count=2 should emit flat memory item_start + item_done."""
    kwargs = _make_stream_loop_kwargs(active_memory_count=2, tools=[])
    events = _run_stream_loop(**kwargs, _provider_pieces=[{"type": "delta", "text": "hi"}])

    # No thinking wrapper
    thinking_events = [e for e in events if e.get("item", {}).get("kind") == "thinking"]
    assert thinking_events == [], "Should not have thinking events"

    # Exactly one item_start with kind='memory'
    memory_starts = [
        e for e in events
        if e.get("type") == "item_start" and e.get("item", {}).get("kind") == "memory"
    ]
    assert len(memory_starts) == 1, f"Expected 1 memory item_start, got {len(memory_starts)}"
    assert memory_starts[0]["item"]["count"] == 2

    # Exactly one item_done with kind='memory'
    memory_dones = [
        e for e in events
        if e.get("type") == "item_done" and e.get("item", {}).get("kind") == "memory"
    ]
    assert len(memory_dones) == 1, f"Expected 1 memory item_done, got {len(memory_dones)}"
    assert memory_dones[0]["item"]["count"] == 2
    assert memory_dones[0]["item"]["status"] == "done"

    # Both share the same uid
    start_uid = memory_starts[0]["item"]["uid"]
    done_uid = memory_dones[0]["item"]["uid"]
    assert start_uid == done_uid, f"uid mismatch: {start_uid} != {done_uid}"
    assert len(start_uid) == 36  # UUID4 format


# ---------------------------------------------------------------------------
# Test 3: web_search emits kind='web_search' not kind='tool_call'
# ---------------------------------------------------------------------------

def test_web_search_item_kind():
    """Tool call with name='web_search' should emit kind='web_search' items."""
    tool_call_piece = {
        "type": "tool_call",
        "tool_call": {
            "name": "web_search",
            "arguments": json.dumps({"query": "oil price"}),
        },
    }

    db = MagicMock()
    conv = MagicMock()
    conv.id = 1

    # web_search tool result
    tool_result = {
        "role": "tool",
        "name": "web_search",
        "content": "Oil prices rose by 5% today according to Reuters.",
        "_used_kbs": [],
    }

    kwargs = _make_stream_loop_kwargs(
        active_memory_count=0,
        tools=[{"name": "web_search"}],
        db=db,
        conv=conv,
    )

    with (
        patch("ai_portal.chat.streaming_service.LlmProviderFactory.create") as mock_provider_factory,
        patch("ai_portal.chat.streaming_service.repo.count_messages_in_conversation", return_value=3),
        patch("ai_portal.chat.streaming_service.should_summarize", return_value=False),
        patch("ai_portal.chat.streaming_service.threading.Thread"),
        patch("ai_portal.chat.streaming_service._dispatch_tool_call", return_value=tool_result),
    ):
        provider = MagicMock()
        mock_provider_factory.return_value = provider

        # First call: returns the tool_call piece; second call returns text delta
        provider.stream_deltas_with_tools.side_effect = [
            iter([tool_call_piece]),
            iter([{"type": "delta", "text": "The oil price is high."}]),
        ]

        raw = list(_stream_loop(**kwargs))

    events = _parse_sse_events(raw)

    # Should have item_start with kind='web_search'
    ws_starts = [
        e for e in events
        if e.get("type") == "item_start" and e.get("item", {}).get("kind") == "web_search"
    ]
    assert len(ws_starts) == 1, f"Expected 1 web_search item_start, got: {ws_starts}"
    assert ws_starts[0]["item"]["query"] == "oil price"

    # Should NOT have any kind='tool_call' events
    tool_call_events = [
        e for e in events
        if e.get("item", {}).get("kind") == "tool_call"
    ]
    assert tool_call_events == [], f"Should not have tool_call events: {tool_call_events}"

    # Should have item_done with kind='web_search'
    ws_dones = [
        e for e in events
        if e.get("type") == "item_done" and e.get("item", {}).get("kind") == "web_search"
    ]
    assert len(ws_dones) == 1
    assert ws_dones[0]["item"]["status"] == "done"
    assert "oil" in ws_dones[0]["item"]["result_snippet"].lower()


# ---------------------------------------------------------------------------
# Test 4: stream_items persisted in extra.stream_items
# ---------------------------------------------------------------------------

def test_stream_items_persisted_in_extra():
    """After streaming with memory + web_search, extra.stream_items should be populated."""
    tool_call_piece = {
        "type": "tool_call",
        "tool_call": {
            "name": "web_search",
            "arguments": json.dumps({"query": "oil price"}),
        },
    }

    db = MagicMock()
    conv = MagicMock()
    conv.id = 1

    tool_result = {
        "role": "tool",
        "name": "web_search",
        "content": "Oil prices rose significantly.",
        "_used_kbs": [],
    }

    kwargs = _make_stream_loop_kwargs(
        active_memory_count=2,
        tools=[{"name": "web_search"}],
        db=db,
        conv=conv,
    )

    added_messages: list = []

    def capture_add(msg):
        added_messages.append(msg)

    db.add.side_effect = capture_add

    with (
        patch("ai_portal.chat.streaming_service.LlmProviderFactory.create") as mock_provider_factory,
        patch("ai_portal.chat.streaming_service.repo.count_messages_in_conversation", return_value=3),
        patch("ai_portal.chat.streaming_service.should_summarize", return_value=False),
        patch("ai_portal.chat.streaming_service.threading.Thread"),
        patch("ai_portal.chat.streaming_service._dispatch_tool_call", return_value=tool_result),
    ):
        provider = MagicMock()
        mock_provider_factory.return_value = provider

        provider.stream_deltas_with_tools.side_effect = [
            iter([tool_call_piece]),
            iter([{"type": "delta", "text": "answer"}]),
        ]

        list(_stream_loop(**kwargs))

    # Find the assistant ChatMessage (last db.add call with role='assistant')
    from ai_portal.chat.model import ChatMessage
    assistant_msgs = [m for m in added_messages if isinstance(m, ChatMessage) and m.role == "assistant"]
    assert assistant_msgs, "No assistant ChatMessage was added to db"

    asst_msg = assistant_msgs[-1]
    assert asst_msg.extra is not None, "extra should not be None"
    stream_items = asst_msg.extra.get("stream_items")
    assert stream_items is not None, f"stream_items missing from extra: {asst_msg.extra}"
    assert len(stream_items) == 2, f"Expected 2 stream_items (memory + web_search), got: {stream_items}"

    # Check memory item
    memory_items = [i for i in stream_items if i.get("kind") == "memory"]
    assert len(memory_items) == 1
    assert memory_items[0]["count"] == 2
    assert "uid" in memory_items[0]

    # Check web_search item
    ws_items = [i for i in stream_items if i.get("kind") == "web_search"]
    assert len(ws_items) == 1
    assert ws_items[0]["query"] == "oil price"
    assert "uid" in ws_items[0]
    assert "result_snippet" in ws_items[0]
    # No 'status' field in persisted items
    assert "status" not in ws_items[0]
