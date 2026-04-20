"""Tests that GeminiNativeChatProvider.stream yields typed ProviderStreamEvent."""

import json
from unittest.mock import MagicMock, patch

from ai_portal.catalog.providers.gemini_native import GeminiNativeChatProvider
from ai_portal.catalog.providers.events import (
    TextDeltaEvent,
    ToolCallRequestEvent,
    UsageEvent,
    IterationCompleteEvent,
    ProviderStreamEvent,
)


def _ns(**kwargs):
    """Build a simple namespace with attribute access."""
    ns = MagicMock(spec=[])
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _make_sdk_chunks():
    """Build minimal SDK-like chunks covering text + function_call + usage."""

    # Chunk 1: text delta
    text_part = MagicMock()
    text_part.text = "hi"
    text_part.thought = None
    text_part.function_call = None

    candidate1 = MagicMock()
    candidate1.content = MagicMock()
    candidate1.content.parts = [text_part]
    candidate1.grounding_metadata = None
    candidate1.finish_reason = None

    chunk1 = MagicMock()
    chunk1.candidates = [candidate1]
    chunk1.usage_metadata = None

    # Chunk 2: function call + usage + finish
    fc_part = MagicMock()
    fc_part.text = None
    fc_part.thought = None
    fc_call = MagicMock()
    fc_call.name = "web_search"
    fc_call.args = {"q": "x"}
    fc_call.id = "fc1"
    fc_part.function_call = fc_call

    candidate2 = MagicMock()
    candidate2.content = MagicMock()
    candidate2.content.parts = [fc_part]
    candidate2.grounding_metadata = None
    candidate2.finish_reason = "STOP"

    usage = MagicMock()
    usage.prompt_token_count = 10
    usage.candidates_token_count = 2
    usage.cached_content_token_count = 0
    usage.thoughts_token_count = 0

    chunk2 = MagicMock()
    chunk2.candidates = [candidate2]
    chunk2.usage_metadata = usage

    return [chunk1, chunk2]


async def test_stream_yields_typed_events():
    """stream() yields TextDeltaEvent, ToolCallRequestEvent, UsageEvent, IterationCompleteEvent."""
    sdk_chunks = _make_sdk_chunks()

    fake_models = MagicMock()
    fake_models.generate_content_stream = MagicMock(return_value=iter(sdk_chunks))

    fake_client = MagicMock()
    fake_client.models = fake_models

    settings = MagicMock()
    settings.gemini_api_key = "fake-key"
    settings.chat_default_api_model = "gemini-2.5-flash"

    with patch("google.genai.Client", return_value=fake_client):
        prov = GeminiNativeChatProvider(settings)
        collected = []
        async for ev in prov.stream(
            messages=[{"role": "user", "content": "hi"}],
            model="gemini-2.5-flash",
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
    assert any(isinstance(e, UsageEvent) and e.input_tokens == 10 for e in collected), (
        f"No UsageEvent with input_tokens=10 in {collected}"
    )
    assert any(isinstance(e, IterationCompleteEvent) for e in collected), (
        f"No IterationCompleteEvent in {collected}"
    )
    assert any(isinstance(e, IterationCompleteEvent) and e.stop_reason == "end_turn" for e in collected), (
        f"No IterationCompleteEvent with stop_reason='end_turn' in {collected}"
    )
