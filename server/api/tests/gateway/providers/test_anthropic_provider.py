"""AnthropicProvider — respx-mocked HTTP adapter tests.

Mocks the Anthropic Messages API at the httpx layer and asserts the adapter:
- sends x-api-key + anthropic-version headers
- pulls system messages into the top-level ``system`` field
- maps the response (text + tool_use blocks, usage with cache tokens,
  stop_reason) → canonical LLMResponse
- streams SSE events (message_start / content_block_* / message_delta) →
  canonical chunks (text/thinking deltas, tool calls, usage, complete)
- exposes list_models + health; rejects embed (no Anthropic embeddings API)
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from ai_portal.gateway.providers.anthropic import (
    ANTHROPIC_VERSION,
    AnthropicProvider,
)
from ai_portal.gateway.types import (
    IterationComplete,
    LLMRequest,
    Message,
    TextBlock,
    TextDelta,
    ThinkingConfig,
    ThinkingDelta,
    ToolCall,
    ToolCallRequest,
    ToolDef,
    UsageChunk,
)

BASE = "https://api.anthropic.com/v1"


def _req(model: str = "claude-opus-4-8", **kw) -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[
            Message(role="system", content=[TextBlock(text="be terse")]),
            Message(role="user", content=[TextBlock(text="hi")]),
        ],
        max_tokens=256,
        **kw,
    )


@pytest.mark.asyncio
async def test_complete_maps_response_usage_and_headers():
    payload = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-4-8",
        "content": [{"type": "text", "text": "yo"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 20,
            "output_tokens": 4,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 6,
        },
    }
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/messages").mock(
            return_value=httpx.Response(200, json=payload)
        )
        p = AnthropicProvider(api_key="sk-ant-x")
        resp = await p.complete_canonical(_req())

    req = route.calls[0].request
    assert req.headers["x-api-key"] == "sk-ant-x"
    assert req.headers["anthropic-version"] == ANTHROPIC_VERSION
    sent = json.loads(req.content.decode())
    # System message pulled out of messages into top-level system field.
    assert sent["system"][0]["text"] == "be terse"
    assert [m["role"] for m in sent["messages"]] == ["user"]
    assert sent["max_tokens"] == 256

    assert resp.provider == "anthropic"
    assert resp.content[0].text == "yo"
    assert resp.usage.input_tokens == 20
    assert resp.usage.output_tokens == 4
    assert resp.usage.cache_read_tokens == 10
    assert resp.usage.cache_write_tokens == 6
    assert resp.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_complete_maps_tool_use_block():
    payload = {
        "id": "msg_t",
        "model": "claude-opus-4-8",
        "content": [
            {"type": "text", "text": "calling"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "search",
                "input": {"q": "cats"},
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/messages").mock(
            return_value=httpx.Response(200, json=payload)
        )
        p = AnthropicProvider(api_key="sk-ant-x")
        resp = await p.complete_canonical(
            _req(tools=[ToolDef(name="search", input_schema={"type": "object"})])
        )

    sent = json.loads(route.calls[0].request.content.decode())
    assert sent["tools"][0]["name"] == "search"
    assert resp.stop_reason == "tool_use"
    assert resp.tool_calls == [
        ToolCall(id="toolu_1", name="search", arguments={"q": "cats"})
    ]


@pytest.mark.asyncio
async def test_thinking_config_serialized():
    payload = {
        "id": "m",
        "model": "claude-opus-4-8",
        "content": [{"type": "text", "text": "x"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/messages").mock(
            return_value=httpx.Response(200, json=payload)
        )
        p = AnthropicProvider(api_key="k")
        await p.complete_canonical(
            _req(thinking=ThinkingConfig(enabled=True, budget_tokens=2048))
        )
    sent = json.loads(route.calls[0].request.content.decode())
    assert sent["thinking"] == {"type": "enabled", "budget_tokens": 2048}


@pytest.mark.asyncio
async def test_stream_text_thinking_tool_usage_complete():
    events = [
        ("message_start", {"message": {"usage": {"input_tokens": 12, "cache_read_input_tokens": 4}}}),
        ("content_block_start", {"index": 0, "content_block": {"type": "text"}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "thinking_delta", "thinking": "hmm"}}),
        ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "Hi"}}),
        ("content_block_stop", {"index": 0}),
        ("content_block_start", {"index": 1, "content_block": {"type": "tool_use", "id": "toolu_9", "name": "calc"}}),
        ("content_block_delta", {"index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"a":'}}),
        ("content_block_delta", {"index": 1, "delta": {"type": "input_json_delta", "partial_json": "1}"}}),
        ("content_block_stop", {"index": 1}),
        ("message_delta", {"delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 7}}),
        ("message_stop", {}),
    ]
    sse = "".join(
        f"event: {name}\ndata: {json.dumps({'type': name, **body})}\n\n"
        for name, body in events
    )
    with respx.mock(base_url=BASE) as mock:
        mock.post("/messages").mock(
            return_value=httpx.Response(200, text=sse)
        )
        p = AnthropicProvider(api_key="k")
        chunks = [c.root async for c in p.stream_canonical(_req(stream=True))]

    assert any(isinstance(c, ThinkingDelta) and c.text == "hmm" for c in chunks)
    assert "".join(c.text for c in chunks if isinstance(c, TextDelta)) == "Hi"

    tool = [c for c in chunks if isinstance(c, ToolCallRequest)]
    assert len(tool) == 1
    assert tool[0].tool_name == "calc"
    assert tool[0].arguments == {"a": 1}

    usage = [c for c in chunks if isinstance(c, UsageChunk)]
    assert usage[0].input_tokens == 12
    assert usage[0].output_tokens == 7
    assert usage[0].cache_read_tokens == 4

    assert isinstance(chunks[-1], IterationComplete)
    assert chunks[-1].stop_reason == "tool_use"


@pytest.mark.asyncio
async def test_stream_http_error_yields_provider_error():
    with respx.mock(base_url=BASE) as mock:
        mock.post("/messages").mock(
            return_value=httpx.Response(529, json={"type": "overloaded_error"})
        )
        p = AnthropicProvider(api_key="k")
        chunks = [c.root async for c in p.stream_canonical(_req(stream=True))]
    assert chunks[0].type == "provider_error"
    assert chunks[0].code == "http_529"


@pytest.mark.asyncio
async def test_list_models_and_health():
    with respx.mock(base_url=BASE) as mock:
        mock.get("/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "claude-opus-4-8", "display_name": "Claude Opus 4.8"}
                    ]
                },
            )
        )
        p = AnthropicProvider(api_key="k")
        models = await p.list_models()
        health = await p.health()
    assert models[0].id == "claude-opus-4-8"
    assert models[0].display_name == "Claude Opus 4.8"
    assert health.healthy is True


@pytest.mark.asyncio
async def test_embed_not_supported():
    p = AnthropicProvider(api_key="k")
    with pytest.raises(NotImplementedError):
        await p.embed(["x"], "claude-opus-4-8")


def test_empty_api_key_rejected():
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="")
