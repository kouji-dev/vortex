"""Native Anthropic provider — protocol compliance tests (mocked SDK)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_settings(api_key: str = "sk-test") -> MagicMock:
    s = MagicMock()
    s.anthropic_api_key = api_key
    s.chat_default_api_model = "claude-3-5-sonnet-20241022"
    return s


def _provider():
    from ai_portal.catalog.providers.anthropic_native import AnthropicNativeChatProvider
    with patch("anthropic.Anthropic"):
        return AnthropicNativeChatProvider(_make_settings())


# ── Fake event classes with the right names ───────────────────────────────────

class _Usage:
    def __init__(self, input_tokens=0, output_tokens=0, cache_creation=0, cache_read=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation
        self.cache_read_input_tokens = cache_read


class RawMessageStartEvent:
    def __init__(self, input_tokens=100):
        self.message = MagicMock()
        self.message.usage = _Usage(input_tokens=input_tokens)


class RawContentBlockStartEvent:
    def __init__(self, btype="text", name=None, block_id=None):
        self.content_block = MagicMock()
        self.content_block.type = btype
        self.content_block.name = name
        self.content_block.id = block_id


class RawContentBlockDeltaEvent:
    def __init__(self, dtype="text_delta", text="", partial_json="", index=0):
        self.delta = MagicMock()
        self.delta.type = dtype
        self.delta.text = text
        self.delta.partial_json = partial_json
        self.index = index


class RawMessageDeltaEvent:
    def __init__(self, output_tokens=5):
        self.usage = MagicMock()
        self.usage.output_tokens = output_tokens


def _text_stream(text: str, input_tokens=100):
    events = [RawMessageStartEvent(input_tokens=input_tokens)]
    events.append(RawContentBlockStartEvent(btype="text"))
    for ch in text:
        events.append(RawContentBlockDeltaEvent(dtype="text_delta", text=ch))
    events.append(RawMessageDeltaEvent(output_tokens=len(text)))
    return events


def _make_stream_ctx(events):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.__iter__ = MagicMock(return_value=iter(events))
    return ctx


def test_stream_emits_delta_events():
    provider = _provider()

    with patch.object(provider._client.messages, "stream", return_value=_make_stream_ctx(_text_stream("Hello!"))):
        pieces = list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "hi"}],
            model="claude-3-5-sonnet-20241022",
        ))

    delta_pieces = [p for p in pieces if p.get("type") == "delta"]
    assert len(delta_pieces) > 0
    combined = "".join(p["text"] for p in delta_pieces)
    assert combined == "Hello!"


def test_stream_emits_usage_event():
    provider = _provider()

    with patch.object(provider._client.messages, "stream", return_value=_make_stream_ctx(_text_stream("hi", input_tokens=100))):
        pieces = list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "hi"}],
            model="claude-3-5-sonnet-20241022",
        ))

    usage_pieces = [p for p in pieces if p.get("type") == "usage"]
    assert len(usage_pieces) == 1
    u = usage_pieces[0]
    assert u["input_tokens"] == 100
    assert u["output_tokens"] == len("hi")


def test_system_prompt_gets_cache_control():
    from ai_portal.catalog.providers.anthropic_native import _build_system_blocks

    blocks = _build_system_blocks("You are a helpful assistant.")
    assert len(blocks) == 1
    assert blocks[0]["type"] == "text"
    assert blocks[0].get("cache_control") == {"type": "ephemeral"}


def test_no_api_key_raises():
    import pytest
    from ai_portal.catalog.providers.anthropic_native import AnthropicNativeChatProvider
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicNativeChatProvider(_make_settings(api_key=""))


def test_tool_last_gets_cache_control():
    """Last tool in the list should receive cache_control for tool schema caching."""
    provider = _provider()

    tools_sent = []

    def fake_stream(**kwargs):
        tools_sent.extend(kwargs.get("tools", []))
        return _make_stream_ctx([])

    with patch.object(provider._client.messages, "stream", side_effect=fake_stream):
        list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "hi"}],
            model="claude-3-5-sonnet-20241022",
            tools=[
                {"type": "function", "function": {"name": "tool_a", "description": "a", "parameters": {"type": "object", "properties": {}, "required": []}}},
                {"type": "function", "function": {"name": "tool_b", "description": "b", "parameters": {"type": "object", "properties": {}, "required": []}}},
            ],
        ))

    assert len(tools_sent) == 2
    assert tools_sent[-1].get("cache_control") == {"type": "ephemeral"}
    assert "cache_control" not in tools_sent[0]


def test_thinking_model_sets_thinking_param():
    """claude-3-7 / claude-opus-4 / claude-sonnet-4 should get thinking enabled."""
    provider = _provider()
    kwargs_sent = {}

    def fake_stream(**kwargs):
        kwargs_sent.update(kwargs)
        return _make_stream_ctx([])

    with patch.object(provider._client.messages, "stream", side_effect=fake_stream):
        list(provider.stream_deltas_with_tools(
            [{"role": "user", "content": "hi"}],
            model="claude-sonnet-4-5",
        ))

    assert kwargs_sent.get("thinking", {}).get("type") == "enabled"
