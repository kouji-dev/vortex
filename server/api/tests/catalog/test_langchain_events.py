"""Tests that LangChainChatProvider.stream yields typed ProviderStreamEvent."""

import pytest
from unittest.mock import MagicMock, patch

from ai_portal.catalog.providers.langchain import LangChainChatProvider
from ai_portal.catalog.providers.events import (
    TextDeltaEvent,
    ToolCallRequestEvent,
    UsageEvent,
    IterationCompleteEvent,
    ProviderStreamEvent,
)


class _FakeChunk:
    """Minimal AIMessageChunk stub."""

    def __init__(self, content="", tool_call_chunks=None, tool_calls=None, usage_metadata=None):
        self.content = content
        self.tool_call_chunks = tool_call_chunks or []
        self.tool_calls = tool_calls or []
        self.usage_metadata = usage_metadata
        self.additional_kwargs = {}


def _make_chunks():
    """Two chunks: plain text + tool call + usage."""
    chunk1 = _FakeChunk(content="hi")

    # Tool call chunk with usage
    chunk2 = _FakeChunk(
        content="",
        tool_calls=[{"id": "c1", "name": "web_search", "args": {"q": "x"}}],
        usage_metadata={"input_tokens": 10, "output_tokens": 2},
    )
    return [chunk1, chunk2]


async def test_stream_yields_typed_events():
    """stream() yields TextDeltaEvent, ToolCallRequestEvent, UsageEvent."""
    chunks = _make_chunks()

    class FakeChat:
        def stream(self, *a, **kw):
            return iter(chunks)

    settings = MagicMock()
    settings.langfuse_public_key = None
    settings.langfuse_secret_key = None

    prov = LangChainChatProvider(settings)

    # Patch _chat_model to return our fake chat (avoids API key requirements).
    with patch.object(prov, "_chat_model", return_value=FakeChat()):
        collected = []
        async for ev in prov.stream(
            messages=[{"role": "user", "content": "hi"}],
            model="openai:gpt-4o",
            settings={},
            tools=None,
        ):
            collected.append(ev.root)

    assert any(isinstance(e, TextDeltaEvent) and e.text == "hi" for e in collected), (
        f"No TextDeltaEvent with text='hi' in {collected}"
    )
    assert any(isinstance(e, ToolCallRequestEvent) and e.tool_name == "web_search" for e in collected), (
        f"No ToolCallRequestEvent with tool_name='web_search' in {collected}"
    )
    assert any(isinstance(e, UsageEvent) and e.output_tokens == 2 for e in collected), (
        f"No UsageEvent with output_tokens=2 in {collected}"
    )
    assert any(isinstance(e, IterationCompleteEvent) for e in collected), (
        f"No IterationCompleteEvent in {collected}"
    )
    assert any(isinstance(e, IterationCompleteEvent) and e.stop_reason == "tool_use" for e in collected), (
        f"No IterationCompleteEvent with stop_reason='tool_use' in {collected}"
    )
