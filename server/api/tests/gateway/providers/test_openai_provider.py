"""OpenAIProvider — respx-mocked HTTP adapter tests.

Mocks the OpenAI REST API at the httpx layer and asserts the adapter:
- translates canonical LLMRequest → OpenAI chat body
- maps the chat.completion response → canonical LLMResponse (text, tool calls,
  usage, stop_reason)
- streams SSE chunks → canonical StreamChunk sequence (text deltas, tool calls,
  usage, iteration_complete)
- embeds + lists models + probes health
- sends the bearer token and never leaks it into the response
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from ai_portal.gateway.providers.openai import OpenAIProvider
from ai_portal.gateway.types import (
    IterationComplete,
    LLMRequest,
    Message,
    TextBlock,
    TextDelta,
    ToolCall,
    ToolCallRequest,
    ToolDef,
    Usage,
    UsageChunk,
)

BASE = "https://api.openai.com/v1"


def _req(model: str = "gpt-5.5", **kw) -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
        **kw,
    )


@pytest.mark.asyncio
async def test_complete_maps_response_and_usage():
    payload = {
        "id": "chatcmpl-abc",
        "model": "gpt-5.5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hello world"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 5,
            "total_tokens": 16,
            "prompt_tokens_details": {"cached_tokens": 3},
        },
    }
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        p = OpenAIProvider(api_key="sk-test")
        resp = await p.complete_canonical(_req())

    assert route.called
    sent = json.loads(route.calls[0].request.content.decode())
    assert sent["model"] == "gpt-5.5"
    assert sent["stream"] is False
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"

    assert resp.provider == "openai"
    assert resp.content[0].text == "hello world"
    assert resp.usage.input_tokens == 11
    assert resp.usage.output_tokens == 5
    assert resp.usage.cache_read_tokens == 3
    assert resp.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_complete_maps_tool_calls():
    payload = {
        "id": "chatcmpl-tool",
        "model": "gpt-5.5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": '{"city":"Paris"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
    }
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json=payload)
        )
        p = OpenAIProvider(api_key="sk-test")
        resp = await p.complete_canonical(
            _req(tools=[ToolDef(name="get_weather", input_schema={"type": "object"})])
        )

    sent = json.loads(route.calls[0].request.content.decode())
    assert sent["tools"][0]["function"]["name"] == "get_weather"
    assert resp.stop_reason == "tool_use"
    assert resp.tool_calls == [
        ToolCall(id="call_1", name="get_weather", arguments={"city": "Paris"})
    ]


@pytest.mark.asyncio
async def test_stream_yields_text_usage_and_complete():
    frames = [
        {"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
        {"choices": [{"index": 0, "delta": {"content": "Hel"}}]},
        {"choices": [{"index": 0, "delta": {"content": "lo"}}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {
            "choices": [],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
        },
    ]
    sse = "".join(f"data: {json.dumps(f)}\n\n" for f in frames) + "data: [DONE]\n\n"

    with respx.mock(base_url=BASE) as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, text=sse, headers={"content-type": "text/event-stream"}
            )
        )
        p = OpenAIProvider(api_key="sk-test")
        chunks = [c.root async for c in p.stream_canonical(_req(stream=True))]

    texts = [c.text for c in chunks if isinstance(c, TextDelta)]
    assert "".join(texts) == "Hello"
    usage = [c for c in chunks if isinstance(c, UsageChunk)]
    assert usage and usage[0].input_tokens == 7 and usage[0].output_tokens == 2
    final = chunks[-1]
    assert isinstance(final, IterationComplete)
    assert final.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_stream_accumulates_split_tool_call_args():
    frames = [
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_9",
                                "function": {"name": "lookup", "arguments": '{"q":'},
                            }
                        ]
                    },
                }
            ]
        },
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": '"cats"}'}}
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
    ]
    sse = "".join(f"data: {json.dumps(f)}\n\n" for f in frames) + "data: [DONE]\n\n"
    with respx.mock(base_url=BASE) as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, text=sse)
        )
        p = OpenAIProvider(api_key="sk-test")
        chunks = [c.root async for c in p.stream_canonical(_req(stream=True))]

    calls = [c for c in chunks if isinstance(c, ToolCallRequest)]
    assert len(calls) == 1
    assert calls[0].tool_name == "lookup"
    assert calls[0].arguments == {"q": "cats"}


@pytest.mark.asyncio
async def test_stream_http_error_yields_provider_error():
    with respx.mock(base_url=BASE) as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )
        p = OpenAIProvider(api_key="sk-test")
        chunks = [c.root async for c in p.stream_canonical(_req(stream=True))]

    assert chunks[0].type == "provider_error"
    assert chunks[0].code == "http_429"


@pytest.mark.asyncio
async def test_embed_returns_vectors_in_index_order():
    payload = {
        "model": "text-embedding-3-small",
        "data": [
            {"index": 1, "embedding": [0.4, 0.5]},
            {"index": 0, "embedding": [0.1, 0.2]},
        ],
        "usage": {"prompt_tokens": 6, "total_tokens": 6},
    }
    with respx.mock(base_url=BASE) as mock:
        route = mock.post("/embeddings").mock(
            return_value=httpx.Response(200, json=payload)
        )
        p = OpenAIProvider(api_key="sk-test")
        out = await p.embed(["a", "b"], "text-embedding-3-small")

    body = json.loads(route.calls[0].request.content.decode())
    assert body["input"] == ["a", "b"]
    assert out.vectors == [[0.1, 0.2], [0.4, 0.5]]
    assert out.usage == Usage(input_tokens=6, total_tokens=6)


@pytest.mark.asyncio
async def test_list_models_and_health():
    with respx.mock(base_url=BASE) as mock:
        mock.get("/models").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": "gpt-5.5"}, {"id": "gpt-5.4-mini"}]}
            )
        )
        p = OpenAIProvider(api_key="sk-test")
        models = await p.list_models()
        health = await p.health()

    assert [m.id for m in models] == ["gpt-5.5", "gpt-5.4-mini"]
    assert health.healthy is True


@pytest.mark.asyncio
async def test_custom_base_url_drives_compatible_backend():
    with respx.mock(base_url="https://api.groq.com/openai/v1") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "x",
                    "model": "llama",
                    "choices": [
                        {"index": 0, "message": {"content": "ok"}, "finish_reason": "stop"}
                    ],
                    "usage": {},
                },
            )
        )
        p = OpenAIProvider(
            api_key="gsk", base_url="https://api.groq.com/openai/v1", name="groq"
        )
        resp = await p.complete_canonical(_req(model="llama"))
    assert route.called
    assert resp.content[0].text == "ok"


def test_empty_api_key_rejected():
    with pytest.raises(ValueError):
        OpenAIProvider(api_key="")
