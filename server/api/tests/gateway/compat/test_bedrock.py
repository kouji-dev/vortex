"""B4: Bedrock Converse compat (``/v1/converse``, ``/v1/converse-stream``).

Tests live without DB — gateway service is stubbed via dependency override
so we exercise pure translation + AWS event-stream wire format.

Bedrock Converse shape reference:
- Request: ``{modelId, messages, system, inferenceConfig, toolConfig}``
- Response: ``{output:{message:{role,content[]}}, stopReason, usage}``
- Stream: AWS event-stream chunks with JSON payloads for ``messageStart``,
  ``contentBlockStart``, ``contentBlockDelta``, ``contentBlockStop``,
  ``messageStop``, ``metadata``.
"""

from __future__ import annotations

import base64
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
    ToolCallRequest,
    ToolUseBlock,
    Usage,
    UsageChunk,
)

# ── stub gateway service ─────────────────────────────────────────────────


class _StubService:
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
        return 1


def _build_app(svc: _StubService) -> FastAPI:
    from ai_portal.gateway.compat.bedrock import (
        get_gateway_service,
        router,
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_gateway_service] = lambda: svc
    return app


# ── /v1/converse non-streaming ───────────────────────────────────────────


def test_converse_basic_round_trip():
    svc = _StubService(
        response=LLMResponse(
            id="msg_01",
            model_used="anthropic.claude-3-5-sonnet-20241022-v2:0",
            provider="bedrock",
            content=[TextBlock(text="hello back")],
            usage=Usage(input_tokens=4, output_tokens=2),
            stop_reason="end_turn",
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [{"role": "user", "content": [{"text": "hi"}]}],
            "inferenceConfig": {
                "maxTokens": 256,
                "temperature": 0.5,
                "topP": 0.9,
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()

    # Bedrock wire shape
    assert body["output"]["message"]["role"] == "assistant"
    assert body["output"]["message"]["content"] == [{"text": "hello back"}]
    assert body["stopReason"] == "end_turn"
    assert body["usage"]["inputTokens"] == 4
    assert body["usage"]["outputTokens"] == 2
    assert body["usage"]["totalTokens"] == 6

    # Captured LLMRequest translation
    assert svc.captured is not None
    assert svc.captured.model == "anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert svc.captured.max_tokens == 256
    assert svc.captured.temperature == 0.5
    assert svc.captured.top_p == 0.9
    assert svc.captured.stream is False
    assert len(svc.captured.messages) == 1
    msg = svc.captured.messages[0]
    assert msg.role == "user"
    block = msg.content[0]
    assert getattr(block, "type") == "text"
    assert getattr(block, "text") == "hi"


def test_converse_system_blocks_become_system_message():
    svc = _StubService(
        response=LLMResponse(
            id="msg_02",
            model_used="meta.llama3-70b",
            provider="bedrock",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse",
        json={
            "modelId": "meta.llama3-70b",
            "system": [{"text": "Be terse."}, {"text": "Cite sources."}],
            "messages": [{"role": "user", "content": [{"text": "hi"}]}],
        },
    )
    assert res.status_code == 200

    msgs = svc.captured.messages
    assert msgs[0].role == "system"
    assert len(msgs[0].content) == 2
    assert getattr(msgs[0].content[0], "text") == "Be terse."
    assert getattr(msgs[0].content[1], "text") == "Cite sources."
    assert msgs[1].role == "user"


def test_converse_stop_sequences_pass_through():
    svc = _StubService(
        response=LLMResponse(
            id="msg_03",
            model_used="anthropic.claude-3-5-sonnet-20241022-v2:0",
            provider="bedrock",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [{"role": "user", "content": [{"text": "hi"}]}],
            "inferenceConfig": {
                "maxTokens": 32,
                "stopSequences": ["END", "STOP"],
            },
        },
    )
    assert res.status_code == 200
    assert svc.captured.stop == ["END", "STOP"]


# ── tool use ─────────────────────────────────────────────────────────────


def test_converse_tools_translation():
    svc = _StubService(
        response=LLMResponse(
            id="msg_04",
            model_used="anthropic.claude-3-5-sonnet-20241022-v2:0",
            provider="bedrock",
            content=[
                ToolUseBlock(id="tu_1", name="get_weather", input={"city": "Tokyo"}),
            ],
            stop_reason="tool_use",
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [{"role": "user", "content": [{"text": "weather Tokyo"}]}],
            "toolConfig": {
                "tools": [
                    {
                        "toolSpec": {
                            "name": "get_weather",
                            "description": "Get weather",
                            "inputSchema": {
                                "json": {
                                    "type": "object",
                                    "properties": {"city": {"type": "string"}},
                                    "required": ["city"],
                                }
                            },
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": "get_weather"}},
            },
        },
    )
    assert res.status_code == 200

    # Inbound tools captured
    assert svc.captured.tools is not None
    assert len(svc.captured.tools) == 1
    t = svc.captured.tools[0]
    assert t.name == "get_weather"
    assert t.description == "Get weather"
    assert t.input_schema["required"] == ["city"]
    assert svc.captured.tool_choice is not None
    assert svc.captured.tool_choice.mode == "tool"
    assert svc.captured.tool_choice.tool_name == "get_weather"

    # Outbound response: tool_use translated to toolUse block
    body = res.json()
    content = body["output"]["message"]["content"]
    assert content[0] == {
        "toolUse": {
            "toolUseId": "tu_1",
            "name": "get_weather",
            "input": {"city": "Tokyo"},
        }
    }
    assert body["stopReason"] == "tool_use"


def test_converse_tool_choice_auto_and_any():
    svc = _StubService(
        response=LLMResponse(
            id="x",
            model_used="m",
            provider="bedrock",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))

    for raw, expected_mode in [
        ({"auto": {}}, "auto"),
        ({"any": {}}, "required"),
    ]:
        res = client.post(
            "/v1/converse",
            json={
                "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "messages": [{"role": "user", "content": [{"text": "hi"}]}],
                "toolConfig": {
                    "tools": [
                        {
                            "toolSpec": {
                                "name": "noop",
                                "description": "",
                                "inputSchema": {"json": {"type": "object"}},
                            }
                        }
                    ],
                    "toolChoice": raw,
                },
            },
        )
        assert res.status_code == 200, res.text
        assert svc.captured.tool_choice.mode == expected_mode


def test_converse_tool_result_inbound():
    """User message with toolResult block translates to ToolResultBlock."""
    svc = _StubService(
        response=LLMResponse(
            id="msg_tr",
            model_used="anthropic.claude-3-5-sonnet-20241022-v2:0",
            provider="bedrock",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [
                {"role": "user", "content": [{"text": "weather"}]},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "tu_1",
                                "name": "get_weather",
                                "input": {"city": "Tokyo"},
                            }
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "toolResult": {
                                "toolUseId": "tu_1",
                                "content": [{"text": "sunny 22C"}],
                                "status": "success",
                            }
                        }
                    ],
                },
            ],
        },
    )
    assert res.status_code == 200

    # second message: assistant with tool_use
    assistant_msg = svc.captured.messages[1]
    assert assistant_msg.role == "assistant"
    tu = assistant_msg.content[0]
    assert getattr(tu, "type") == "tool_use"
    assert getattr(tu, "id") == "tu_1"
    assert getattr(tu, "name") == "get_weather"
    assert getattr(tu, "input") == {"city": "Tokyo"}

    # third message: user with tool_result
    user_msg = svc.captured.messages[2]
    tr = user_msg.content[0]
    assert getattr(tr, "type") == "tool_result"
    assert getattr(tr, "tool_use_id") == "tu_1"
    assert getattr(tr, "content") == "sunny 22C"
    assert getattr(tr, "is_error") is False


def test_converse_tool_result_error_status():
    svc = _StubService(
        response=LLMResponse(
            id="msg_tr2",
            model_used="m",
            provider="bedrock",
            content=[TextBlock(text="ok")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "toolResult": {
                                "toolUseId": "tu_x",
                                "content": [{"text": "boom"}],
                                "status": "error",
                            }
                        }
                    ],
                },
            ],
        },
    )
    assert res.status_code == 200
    tr = svc.captured.messages[0].content[0]
    assert getattr(tr, "is_error") is True


# ── vision ───────────────────────────────────────────────────────────────


def test_converse_image_source_bytes_translation():
    """Bedrock image block uses {image:{format,source:{bytes:<b64>}}}."""
    svc = _StubService(
        response=LLMResponse(
            id="msg_img",
            model_used="anthropic.claude-3-5-sonnet-20241022-v2:0",
            provider="bedrock",
            content=[TextBlock(text="describes")],
        ),
    )
    raw_bytes = b"\x89PNG\r\n\x1a\n"
    b64 = base64.b64encode(raw_bytes).decode("ascii")

    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": "png",
                                "source": {"bytes": b64},
                            }
                        },
                        {"text": "what is this?"},
                    ],
                }
            ],
        },
    )
    assert res.status_code == 200
    blocks = svc.captured.messages[0].content
    img = blocks[0]
    assert getattr(img, "type") == "image"
    assert getattr(img, "media_type") == "image/png"
    assert getattr(img, "data_base64") == b64
    txt = blocks[1]
    assert getattr(txt, "type") == "text"
    assert getattr(txt, "text") == "what is this?"


def test_converse_response_serialises_image_block():
    """Assistant image content (rare) round-trips to image source bytes."""
    from ai_portal.gateway.types import ImageBlock

    svc = _StubService(
        response=LLMResponse(
            id="msg_img_out",
            model_used="m",
            provider="bedrock",
            content=[ImageBlock(data_base64="ZmFrZQ==", media_type="image/jpeg")],
        ),
    )
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [{"role": "user", "content": [{"text": "hi"}]}],
        },
    )
    body = res.json()
    content = body["output"]["message"]["content"]
    assert content[0] == {
        "image": {
            "format": "jpeg",
            "source": {"bytes": "ZmFrZQ=="},
        }
    }


# ── streaming ────────────────────────────────────────────────────────────


def _parse_aws_event_stream(raw: bytes) -> list[dict[str, Any]]:
    """Parse the simplified AWS event-stream format the gateway emits.

    Each event is encoded as one line per event, format::

        :event-type:<name>\n
        <json-payload>\n
        \n

    Real AWS event-stream uses a binary framing protocol; for tests we
    emit a readable but unambiguous text variant. The gateway exposes
    both a binary writer (production) and this text reader-compatible
    output via the ``X-Amzn-EventStream-Text`` content-type variant.
    """
    text = raw.decode("utf-8")
    events: list[dict[str, Any]] = []
    cur_event: str | None = None
    for line in text.split("\n"):
        if line.startswith(":event-type:"):
            cur_event = line[len(":event-type:") :].strip()
        elif line.strip() == "":
            cur_event = None
        elif cur_event is not None:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = {"raw": line}
            events.append({"event": cur_event, "data": payload})
            cur_event = None
    return events


def test_converse_stream_basic_text_events():
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
        "/v1/converse-stream",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [{"role": "user", "content": [{"text": "hi"}]}],
            "inferenceConfig": {"maxTokens": 32},
        },
    )
    assert res.status_code == 200
    ct = res.headers["content-type"]
    assert "application/vnd.amazon.eventstream" in ct

    events = _parse_aws_event_stream(res.content)
    names = [e["event"] for e in events]

    # Expected Bedrock Converse stream sequence
    assert names[0] == "messageStart"
    assert "contentBlockDelta" in names
    assert "contentBlockStop" in names
    assert "messageStop" in names
    assert names[-1] == "metadata"

    # messageStart carries role
    ms = next(e for e in events if e["event"] == "messageStart")
    assert ms["data"]["role"] == "assistant"

    # contentBlockDelta carries text deltas
    deltas = [e for e in events if e["event"] == "contentBlockDelta"]
    assert len(deltas) == 2
    assert deltas[0]["data"]["delta"]["text"] == "Hel"
    assert deltas[1]["data"]["delta"]["text"] == "lo"
    assert deltas[0]["data"]["contentBlockIndex"] == 0

    # messageStop carries stopReason
    mstop = next(e for e in events if e["event"] == "messageStop")
    assert mstop["data"]["stopReason"] == "end_turn"

    # metadata carries usage
    md = next(e for e in events if e["event"] == "metadata")
    assert md["data"]["usage"]["inputTokens"] == 3
    assert md["data"]["usage"]["outputTokens"] == 2
    assert md["data"]["usage"]["totalTokens"] == 5


def test_converse_stream_tool_use_emits_input_delta():
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
        "/v1/converse-stream",
        json={
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "messages": [{"role": "user", "content": [{"text": "weather?"}]}],
        },
    )
    assert res.status_code == 200
    events = _parse_aws_event_stream(res.content)

    # contentBlockStart carries toolUse info
    cbs = next(e for e in events if e["event"] == "contentBlockStart")
    start = cbs["data"]["start"]
    assert "toolUse" in start
    assert start["toolUse"]["toolUseId"] == "tu_1"
    assert start["toolUse"]["name"] == "get_weather"

    # contentBlockDelta carries inputJsonDelta with full args
    cbd = next(
        e
        for e in events
        if e["event"] == "contentBlockDelta" and "toolUse" in e["data"]["delta"]
    )
    raw_json = cbd["data"]["delta"]["toolUse"]["input"]
    assert json.loads(raw_json) == {"city": "Tokyo"}

    mstop = next(e for e in events if e["event"] == "messageStop")
    assert mstop["data"]["stopReason"] == "tool_use"


def test_converse_stream_request_marks_stream_true():
    svc = _StubService(chunks=[IterationComplete(stop_reason="end_turn")])
    client = TestClient(_build_app(svc))
    res = client.post(
        "/v1/converse-stream",
        json={
            "modelId": "m",
            "messages": [{"role": "user", "content": [{"text": "hi"}]}],
        },
    )
    assert res.status_code == 200
    assert svc.captured.stream is True
