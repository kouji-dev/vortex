"""B3: Anthropic-compatible ``/v1/messages`` (+ ``count_tokens``).

Tests live without DB — the gateway service is stubbed via dependency
override so we exercise pure translation + SSE wire format.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.gateway.types import (
    IterationComplete,
    LLMRequest,
    LLMResponse,
    TextBlock,
    TextDelta,
    ThinkingDelta,
    ToolCallRequest,
    Usage,
    UsageChunk,
)

# ── stub gateway service ─────────────────────────────────────────────────


class _StubService:
    """Test double for the gateway dispatcher.

    The real gateway service is wired in later phases. For B3 we only
    care that the compat layer:
    - builds a correct :class:`LLMRequest`
    - serialises :class:`LLMResponse` / :class:`StreamChunk`'s to the
      Anthropic wire shape.
    """

    def __init__(
        self,
        *,
        response: LLMResponse | None = None,
        chunks: list[Any] | None = None,
    ) -> None:
        self.response = response
        self.chunks = chunks or []
        self.captured: LLMRequest | None = None

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.captured = req
        assert self.response is not None, "stub: response not configured"
        return self.response

    async def stream(self, req: LLMRequest) -> AsyncIterator[Any]:
        self.captured = req
        for c in self.chunks:
            yield c

    def count_tokens(self, req: LLMRequest) -> int:
        self.captured = req
        # Naive: sum text lengths / 4.
        n = 0
        for m in req.messages:
            for b in m.content:
                if getattr(b, "type", None) == "text":
                    n += len(getattr(b, "text", "")) // 4
        return max(1, n)


def _build_app(svc: _StubService) -> FastAPI:
    from ai_portal.gateway.compat.anthropic import (
        get_gateway_service,
        router,
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_gateway_service] = lambda: svc
    return app


# ── non-streaming ────────────────────────────────────────────────────────


def test_messages_non_streaming_basic():
    svc = _StubService(
        response=LLMResponse(
            id="msg_01",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="hello back")],
            usage=Usage(input_tokens=4, output_tokens=2),
            stop_reason="end_turn",
        ),
    )
    client = TestClient(_build_app(svc))

    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["type"] == "message"
    assert body["role"] == "assistant"
    assert body["model"] == "claude-sonnet-4-6"
    assert body["content"] == [{"type": "text", "text": "hello back"}]
    assert body["stop_reason"] == "end_turn"
    assert body["usage"]["input_tokens"] == 4
    assert body["usage"]["output_tokens"] == 2

    # Captured request: user message routed correctly.
    assert svc.captured is not None
    assert svc.captured.model == "claude-sonnet-4-6"
    assert svc.captured.max_tokens == 32
    assert svc.captured.stream is False
    assert len(svc.captured.messages) == 1
    assert svc.captured.messages[0].role == "user"
    first_block = svc.captured.messages[0].content[0]
    assert getattr(first_block, "type", None) == "text"
    assert getattr(first_block, "text", None) == "hi"


def test_messages_system_prompt_string_form():
    svc = _StubService(
        response=LLMResponse(
            id="msg_02",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 10,
            "system": "Be terse.",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200

    msgs = svc.captured.messages
    assert msgs[0].role == "system"
    assert getattr(msgs[0].content[0], "text") == "Be terse."
    assert msgs[1].role == "user"


def test_messages_cache_control_on_system_blocks_to_cache_hints():
    svc = _StubService(
        response=LLMResponse(
            id="msg_03",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 16,
            "system": [
                {
                    "type": "text",
                    "text": "Long stable prompt.",
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200

    sys_block = svc.captured.messages[0].content[0]
    assert getattr(sys_block, "type") == "text"
    cc = getattr(sys_block, "cache_control")
    assert cc is not None
    assert cc.ttl == "5m"

    # And request-level cache_hints set.
    assert svc.captured.cache_hints is not None
    assert len(svc.captured.cache_hints) >= 1


def test_messages_cache_control_one_hour_ttl():
    svc = _StubService(
        response=LLMResponse(
            id="msg_03b",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 16,
            "system": [
                {
                    "type": "text",
                    "text": "Stable.",
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ],
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200
    sys_block = svc.captured.messages[0].content[0]
    cc = getattr(sys_block, "cache_control")
    assert cc.ttl == "1h"


def test_messages_thinking_config_translation():
    svc = _StubService(
        response=LLMResponse(
            id="msg_04",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "thinking": {"type": "enabled", "budget_tokens": 4000},
            "messages": [{"role": "user", "content": "solve x"}],
        },
    )
    assert res.status_code == 200
    assert svc.captured.thinking is not None
    assert svc.captured.thinking.enabled is True
    assert svc.captured.thinking.budget_tokens == 4000


def test_messages_thinking_disabled_translation():
    svc = _StubService(
        response=LLMResponse(
            id="msg_04b",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200
    assert svc.captured.thinking is not None
    assert svc.captured.thinking.enabled is False


def test_messages_image_content_block_to_image_block():
    svc = _StubService(
        response=LLMResponse(
            id="msg_05",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="describes image")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 64,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "iVBORw0KGgo=",
                            },
                        },
                        {"type": "text", "text": "what is this?"},
                    ],
                }
            ],
        },
    )
    assert res.status_code == 200

    blocks = svc.captured.messages[0].content
    assert len(blocks) == 2
    image_b = blocks[0]
    assert getattr(image_b, "type") == "image"
    assert getattr(image_b, "media_type") == "image/png"
    assert getattr(image_b, "data_base64") == "iVBORw0KGgo="
    txt_b = blocks[1]
    assert getattr(txt_b, "type") == "text"
    assert getattr(txt_b, "text") == "what is this?"


def test_messages_image_url_source():
    svc = _StubService(
        response=LLMResponse(
            id="msg_05b",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 16,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": "https://example.com/cat.png",
                            },
                        },
                    ],
                }
            ],
        },
    )
    assert res.status_code == 200
    image_b = svc.captured.messages[0].content[0]
    assert getattr(image_b, "url") == "https://example.com/cat.png"


def test_messages_tools_and_tool_choice_translate():
    svc = _StubService(
        response=LLMResponse(
            id="msg_06",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[],
            tool_calls=[],
            stop_reason="tool_use",
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 64,
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Get weather",
                    "input_schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                }
            ],
            "tool_choice": {"type": "tool", "name": "get_weather"},
            "messages": [{"role": "user", "content": "weather in Tokyo"}],
        },
    )
    assert res.status_code == 200

    assert svc.captured.tools is not None
    assert len(svc.captured.tools) == 1
    t = svc.captured.tools[0]
    assert t.name == "get_weather"
    assert t.description == "Get weather"
    assert t.input_schema["required"] == ["city"]

    assert svc.captured.tool_choice is not None
    assert svc.captured.tool_choice.mode == "tool"
    assert svc.captured.tool_choice.tool_name == "get_weather"


def test_messages_tool_choice_auto_and_any():
    svc = _StubService(
        response=LLMResponse(
            id="x",
            model_used="m",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))

    for raw, expected in [
        ({"type": "auto"}, "auto"),
        ({"type": "none"}, "none"),
        ({"type": "any"}, "required"),
    ]:
        res = client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 8,
                "tool_choice": raw,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert res.status_code == 200, res.text
        assert svc.captured.tool_choice.mode == expected


def test_messages_response_with_tool_use_block_serialises():
    """Assistant tool_use block in response → Anthropic wire format."""
    from ai_portal.gateway.types import ToolUseBlock

    svc = _StubService(
        response=LLMResponse(
            id="msg_07",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[
                TextBlock(text="let me check"),
                ToolUseBlock(id="tu_1", name="get_weather", input={"city": "Tokyo"}),
            ],
            stop_reason="tool_use",
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "messages": [{"role": "user", "content": "weather"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["stop_reason"] == "tool_use"
    assert body["content"][0] == {"type": "text", "text": "let me check"}
    assert body["content"][1] == {
        "type": "tool_use",
        "id": "tu_1",
        "name": "get_weather",
        "input": {"city": "Tokyo"},
    }


def test_messages_tool_result_block_translation():
    """Inbound user message with tool_result block translates to ToolResultBlock."""
    svc = _StubService(
        response=LLMResponse(
            id="msg_07b",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 16,
            "messages": [
                {"role": "user", "content": "weather"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tu_1",
                            "name": "get_weather",
                            "input": {"city": "Tokyo"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu_1",
                            "content": "sunny 22C",
                        }
                    ],
                },
            ],
        },
    )
    assert res.status_code == 200
    # Third message should be the tool_result.
    last = svc.captured.messages[-1]
    assert last.role == "user"
    tr = last.content[0]
    assert getattr(tr, "type") == "tool_result"
    assert getattr(tr, "tool_use_id") == "tu_1"
    assert getattr(tr, "content") == "sunny 22C"


# ── streaming ────────────────────────────────────────────────────────────


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    """Parse Anthropic SSE stream into a list of {event, data} dicts."""
    events: list[dict[str, Any]] = []
    cur_event: str | None = None
    for line in raw.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("event:"):
            cur_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            payload = line[len("data:") :].strip()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {"raw": payload}
            events.append({"event": cur_event, "data": data})
            cur_event = None
        elif line == "":
            cur_event = None
    return events


def test_messages_streaming_emits_anthropic_sse_events():
    svc = _StubService(
        chunks=[
            TextDelta(text="Hel"),
            TextDelta(text="lo"),
            UsageChunk(input_tokens=3, output_tokens=2),
            IterationComplete(stop_reason="end_turn"),
        ],
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(res.text)
    names = [e["event"] for e in events]

    assert names[0] == "message_start"
    assert "content_block_start" in names
    assert "content_block_delta" in names
    assert "content_block_stop" in names
    assert "message_delta" in names
    assert names[-1] == "message_stop"

    # First content_block_start has empty text block.
    cbs = next(e for e in events if e["event"] == "content_block_start")
    assert cbs["data"]["index"] == 0
    assert cbs["data"]["content_block"]["type"] == "text"

    # text deltas
    text_deltas = [
        e
        for e in events
        if e["event"] == "content_block_delta"
        and e["data"]["delta"]["type"] == "text_delta"
    ]
    assert len(text_deltas) == 2
    assert text_deltas[0]["data"]["delta"]["text"] == "Hel"
    assert text_deltas[1]["data"]["delta"]["text"] == "lo"

    # message_delta carries stop_reason + usage
    md = next(e for e in events if e["event"] == "message_delta")
    assert md["data"]["delta"]["stop_reason"] == "end_turn"
    assert md["data"]["usage"]["output_tokens"] == 2


def test_messages_streaming_thinking_delta_emits_thinking_block():
    svc = _StubService(
        chunks=[
            ThinkingDelta(text="reasoning..."),
            TextDelta(text="answer"),
            IterationComplete(stop_reason="end_turn"),
        ],
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "stream": True,
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200
    events = _parse_sse(res.text)

    # We expect a thinking content block first (index 0), then text (index 1).
    starts = [e for e in events if e["event"] == "content_block_start"]
    assert starts[0]["data"]["content_block"]["type"] == "thinking"
    assert starts[1]["data"]["content_block"]["type"] == "text"

    thinking_deltas = [
        e
        for e in events
        if e["event"] == "content_block_delta"
        and e["data"]["delta"]["type"] == "thinking_delta"
    ]
    assert len(thinking_deltas) == 1
    assert thinking_deltas[0]["data"]["delta"]["thinking"] == "reasoning..."


def test_messages_streaming_tool_use_emits_input_json_delta():
    svc = _StubService(
        chunks=[
            ToolCallRequest(
                call_id="tu_1",
                tool_name="get_weather",
                arguments={"city": "Tokyo"},
            ),
            IterationComplete(stop_reason="tool_use"),
        ],
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 32,
            "stream": True,
            "messages": [{"role": "user", "content": "weather?"}],
        },
    )
    assert res.status_code == 200
    events = _parse_sse(res.text)

    cbs = next(e for e in events if e["event"] == "content_block_start")
    cb = cbs["data"]["content_block"]
    assert cb["type"] == "tool_use"
    assert cb["id"] == "tu_1"
    assert cb["name"] == "get_weather"

    # input_json_delta carries partial_json (full args dumped once)
    cbd = next(
        e
        for e in events
        if e["event"] == "content_block_delta"
        and e["data"]["delta"]["type"] == "input_json_delta"
    )
    assert json.loads(cbd["data"]["delta"]["partial_json"]) == {"city": "Tokyo"}

    md = next(e for e in events if e["event"] == "message_delta")
    assert md["data"]["delta"]["stop_reason"] == "tool_use"


# ── count_tokens ─────────────────────────────────────────────────────────


def test_count_tokens_endpoint():
    svc = _StubService()
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages/count_tokens",
        json={
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "user", "content": "hello world this is a longer message"}
            ],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "input_tokens" in body
    assert isinstance(body["input_tokens"], int)
    assert body["input_tokens"] >= 1


# ── headers ──────────────────────────────────────────────────────────────


def test_messages_passes_anthropic_headers_to_metadata():
    svc = _StubService(
        response=LLMResponse(
            id="msg_h",
            model_used="claude-sonnet-4-6",
            provider="anthropic",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/messages",
        headers={
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31,messages-2024-11",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert res.status_code == 200
    md = svc.captured.metadata
    assert md.get("anthropic_version") == "2023-06-01"
    assert "prompt-caching-2024-07-31" in md.get("anthropic_beta", [])
    assert "messages-2024-11" in md.get("anthropic_beta", [])
