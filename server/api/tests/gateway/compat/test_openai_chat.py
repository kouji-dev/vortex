"""B1: OpenAI-compatible /v1/chat/completions tests.

Verify request shape → LLMRequest translation, response shape → OpenAI
``chat.completion`` shape, streaming SSE ``data: ...\\n\\n`` framing.

The provider layer is stubbed via a fake :class:`LLMProvider` injected through
the gateway service dependency — tests stay at the HTTP boundary, do not touch
real provider HTTP, and do not require a DB.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.gateway.compat.openai import router as openai_router
from ai_portal.gateway.service import get_llm_provider
from ai_portal.gateway.types import (
    Capability,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TextBlock,
    Usage,
)

# ── fakes ────────────────────────────────────────────────────────────────


class _RecordingProvider:
    """Captures the LLMRequest passed in; returns a canned LLMResponse / stream."""

    name = "fake"
    capabilities: set[Capability] = {"chat", "streaming"}

    def __init__(self, *, text: str = "hello back"):
        self._text = text
        self.last_request: LLMRequest | None = None

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        self.last_request = req
        return LLMResponse(
            id="resp_abc",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text=self._text)],
            tool_calls=[],
            usage=Usage(input_tokens=5, output_tokens=4, total_tokens=9),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(self, req: LLMRequest) -> AsyncIterator[StreamChunk]:
        self.last_request = req
        # Yield two text deltas + iteration_complete + usage.
        for chunk in (
            {"type": "text_delta", "text": "hel"},
            {"type": "text_delta", "text": "lo"},
            {
                "type": "usage",
                "input_tokens": 5,
                "output_tokens": 2,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
            },
            {"type": "iteration_complete", "stop_reason": "end_turn"},
        ):
            yield StreamChunk.model_validate(chunk)

    async def embed(self, texts, model):  # pragma: no cover — not used in chat tests
        raise NotImplementedError

    def count_tokens(self, text, model):  # pragma: no cover
        return max(1, len(text) // 4)

    async def list_models(self):  # pragma: no cover
        return []

    async def health(self):  # pragma: no cover
        from ai_portal.gateway.types import HealthStatus
        return HealthStatus(healthy=True)


def _build_app(provider: _RecordingProvider) -> FastAPI:
    app = FastAPI()
    app.include_router(openai_router)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return app


# ── non-streaming ────────────────────────────────────────────────────────


def test_openai_chat_completions_non_streaming():
    provider = _RecordingProvider(text="hi there")
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/chat/completions",
        json={
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "system", "content": "You are caveman."},
                {"role": "user", "content": "hi"},
            ],
            "max_tokens": 256,
            "temperature": 0.2,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # OpenAI shape
    assert body["object"] == "chat.completion"
    assert body["id"]
    assert body["model"] == "claude-sonnet-4-6"
    assert isinstance(body["choices"], list) and len(body["choices"]) == 1
    choice = body["choices"][0]
    assert choice["index"] == 0
    assert choice["message"]["role"] == "assistant"
    assert choice["message"]["content"] == "hi there"
    assert choice["finish_reason"] == "stop"
    # usage shape
    assert body["usage"]["prompt_tokens"] == 5
    assert body["usage"]["completion_tokens"] == 4
    assert body["usage"]["total_tokens"] == 9

    # request shape → LLMRequest
    req = provider.last_request
    assert req is not None
    assert req.model == "claude-sonnet-4-6"
    assert len(req.messages) == 2
    assert req.messages[0].role == "system"
    assert req.messages[1].role == "user"
    # content normalized to TextBlock list
    assert req.messages[1].content[0].text == "hi"
    assert req.max_tokens == 256
    assert req.temperature == 0.2
    assert req.stream is False


def test_openai_chat_completions_with_content_blocks():
    """OpenAI accepts content as a list of {type:text,text:...} blocks."""
    provider = _RecordingProvider()
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/chat/completions",
        json={
            "model": "x",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "part1"},
                        {"type": "text", "text": "part2"},
                    ],
                }
            ],
        },
    )
    assert res.status_code == 200
    req = provider.last_request
    assert req is not None
    assert len(req.messages[0].content) == 2
    assert req.messages[0].content[0].text == "part1"
    assert req.messages[0].content[1].text == "part2"


def test_openai_chat_completions_honors_request_id_header():
    """``x-request-id`` is echoed back on the response."""
    provider = _RecordingProvider()
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/chat/completions",
        headers={"x-request-id": "req-xyz-123"},
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == "req-xyz-123"


def test_openai_chat_completions_honors_organization_header():
    """``openai-organization`` is captured into the LLMRequest metadata."""
    provider = _RecordingProvider()
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/chat/completions",
        headers={"openai-organization": "org_42"},
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 200
    req = provider.last_request
    assert req is not None
    assert req.metadata.get("openai_organization") == "org_42"


def test_openai_chat_completions_honors_traceparent_header():
    """``traceparent`` is captured into metadata for downstream propagation."""
    provider = _RecordingProvider()
    client = TestClient(_build_app(provider))

    tp = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    res = client.post(
        "/v1/chat/completions",
        headers={"traceparent": tp},
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 200
    req = provider.last_request
    assert req is not None
    assert req.metadata.get("traceparent") == tp


# ── streaming ────────────────────────────────────────────────────────────


def _parse_sse(body: str) -> list[dict]:
    """Parse SSE ``data: ...\\n\\n`` framing into list of JSON dicts (skip [DONE])."""
    events: list[dict] = []
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Each chunk should start with "data: "
        assert chunk.startswith("data: "), f"bad SSE frame: {chunk!r}"
        payload = chunk[len("data: "):]
        if payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


def test_openai_chat_completions_streaming_sse():
    provider = _RecordingProvider()
    client = TestClient(_build_app(provider))

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    ) as res:
        assert res.status_code == 200
        ctype = res.headers.get("content-type", "")
        assert "text/event-stream" in ctype, ctype
        body = res.read().decode()

    events = _parse_sse(body)
    # First event must declare role:assistant.
    assert events[0]["object"] == "chat.completion.chunk"
    assert events[0]["choices"][0]["delta"].get("role") == "assistant"

    # Text deltas
    text_deltas = [
        e["choices"][0]["delta"].get("content")
        for e in events
        if e["choices"][0]["delta"].get("content")
    ]
    assert "".join(d for d in text_deltas if d) == "hello"

    # Last event has finish_reason set.
    last = events[-1]
    assert last["choices"][0]["finish_reason"] == "stop"

    # SSE terminator [DONE] must be present.
    assert "data: [DONE]" in body

    # Request was marked stream=True.
    assert provider.last_request is not None
    assert provider.last_request.stream is True


def test_openai_chat_completions_streaming_includes_usage():
    """When stream_options.include_usage=True, final chunk carries usage."""
    provider = _RecordingProvider()
    client = TestClient(_build_app(provider))

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        },
    ) as res:
        body = res.read().decode()
    events = _parse_sse(body)
    # Find at least one event with usage populated.
    usage_events = [e for e in events if e.get("usage")]
    assert usage_events, body
    u = usage_events[-1]["usage"]
    assert u["prompt_tokens"] == 5
    assert u["completion_tokens"] == 2


# ── error / edge cases ────────────────────────────────────────────────────


def test_openai_chat_completions_rejects_empty_messages():
    provider = _RecordingProvider()
    client = TestClient(_build_app(provider))

    res = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": []},
    )
    assert res.status_code == 422
