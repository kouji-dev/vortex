"""OpenAI HTTP adapter — canonical :class:`LLMProvider` over raw httpx.

Wraps the OpenAI REST API directly (no SDK) so every call is mockable with
``respx`` at the httpx layer and we keep one tight code path for the gateway.

Implements the canonical gateway protocol:

- :meth:`complete_canonical` → ``POST /v1/chat/completions``
- :meth:`stream_canonical`   → ``POST /v1/chat/completions`` (``stream=true`` SSE)
- :meth:`embed`              → ``POST /v1/embeddings``
- :meth:`count_tokens`       → local heuristic (no network)
- :meth:`list_models`        → ``GET /v1/models``
- :meth:`health`             → ``GET /v1/models`` (lightweight probe)

Translation: canonical :class:`LLMRequest` → OpenAI chat body on the way in,
OpenAI ``chat.completion`` / SSE chunks → canonical types on the way out.

Secrets never appear in logs. The bearer token lives only in the auth header.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    HealthStatus,
    ImageBlock,
    IterationComplete,
    LLMRequest,
    LLMResponse,
    Message,
    ModelInfo,
    ProviderError,
    StreamChunk,
    TextBlock,
    TextDelta,
    ToolCall,
    ToolCallRequest,
    Usage,
    UsageChunk,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
# Conservative default; callers should pass ``max_tokens`` explicitly.
_DEFAULT_MAX_TOKENS = 4096
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

# OpenAI finish_reason → canonical stop_reason.
_FINISH_TO_STOP: dict[str, str] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "content_filter",
}


def _stop_from_finish(finish: str | None) -> str:
    return _FINISH_TO_STOP.get(finish or "", "end_turn")


class OpenAIProvider:
    """OpenAI-compatible provider speaking the canonical gateway protocol.

    ``base_url`` lets this same adapter drive any OpenAI-compatible backend
    (Together, Groq, Fireworks, vLLM, Azure-style proxies) by pointing at a
    different host — the wire shape is identical.
    """

    name: str = "openai"
    capabilities: set[Capability] = {
        "chat",
        "streaming",
        "tools",
        "vision",
        "json_mode",
        "json_schema",
        "embeddings",
        "parallel_tools",
    }

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        organization: str | None = None,
        name: str = "openai",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAIProvider requires a non-empty api_key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._organization = organization
        self.name = name
        # Injected client is used as-is (tests); else lazily created per call.
        self._client = client

    # ── http plumbing ──────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._organization:
            h["OpenAI-Organization"] = self._organization
        return h

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=_TIMEOUT)

    # ── request translation ────────────────────────────────────────────────

    def _build_body(self, req: LLMRequest, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": req.model,
            "messages": [_message_to_openai(m) for m in req.messages],
            "max_tokens": req.max_tokens or _DEFAULT_MAX_TOKENS,
            "stream": stream,
        }
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.top_p is not None:
            body["top_p"] = req.top_p
        if req.stop:
            body["stop"] = req.stop
        if req.user:
            body["user"] = req.user
        if req.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema or {"type": "object"},
                    },
                }
                for t in req.tools
            ]
        if req.tool_choice is not None:
            body["tool_choice"] = _tool_choice_to_openai(req.tool_choice)
        if req.response_format is not None:
            body["response_format"] = _response_format_to_openai(req.response_format)
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    # ── completion ─────────────────────────────────────────────────────────

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        body = self._build_body(req, stream=False)
        url = f"{self._base_url}/chat/completions"
        client = self._client or self._new_client()
        try:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._client is None:
                await client.aclose()
        return _response_from_openai(data, default_model=req.model)

    async def stream_canonical(
        self, req: LLMRequest
    ) -> AsyncIterator[StreamChunk]:
        body = self._build_body(req, stream=True)
        url = f"{self._base_url}/chat/completions"
        client = self._client or self._new_client()
        # Accumulate streamed tool-call fragments (OpenAI splits arguments
        # across deltas, keyed by choice index).
        tool_buf: dict[int, dict[str, Any]] = {}
        finish: str | None = None
        usage_seen = False
        try:
            async with client.stream(
                "POST", url, headers=self._headers(), json=body
            ) as r:
                if r.status_code >= 400:
                    detail = (await r.aread()).decode("utf-8", "replace")
                    yield StreamChunk(
                        root=ProviderError(
                            code=f"http_{r.status_code}", message=detail[:500]
                        )
                    )
                    return
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    for sc in _stream_chunks_from_openai(chunk, tool_buf):
                        if isinstance(sc.root, UsageChunk):
                            usage_seen = True
                        yield sc
                    # Capture finish_reason for the terminal iteration_complete.
                    for ch in chunk.get("choices") or []:
                        fr = ch.get("finish_reason")
                        if fr:
                            finish = fr
        except httpx.HTTPError as exc:
            yield StreamChunk(
                root=ProviderError(code=type(exc).__name__, message=str(exc))
            )
            return
        finally:
            if self._client is None:
                await client.aclose()

        # Flush any completed tool-call buffers as canonical chunks.
        for tc in tool_buf.values():
            if tc.get("name"):
                yield StreamChunk(
                    root=ToolCallRequest(
                        call_id=tc.get("id", ""),
                        tool_name=tc["name"],
                        arguments=_safe_json_args(tc.get("arguments", "")),
                    )
                )
        if not usage_seen:
            yield StreamChunk(root=UsageChunk())
        yield StreamChunk(
            root=IterationComplete(stop_reason=_stop_from_finish(finish))  # type: ignore[arg-type]
        )

    # ── embeddings ─────────────────────────────────────────────────────────

    async def embed(self, texts: list[str], model: str) -> Embeddings:
        url = f"{self._base_url}/embeddings"
        body: dict[str, Any] = {"model": model, "input": texts}
        client = self._client or self._new_client()
        try:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._client is None:
                await client.aclose()
        rows = sorted(
            data.get("data", []), key=lambda d: d.get("index", 0)
        )
        vectors = [list(map(float, row.get("embedding", []))) for row in rows]
        usage = data.get("usage", {}) or {}
        return Embeddings(
            model=data.get("model", model),
            provider=self.name,
            vectors=vectors,
            usage=Usage(
                input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                total_tokens=int(usage.get("total_tokens", 0) or 0),
            ),
        )

    # ── introspection ──────────────────────────────────────────────────────

    def count_tokens(self, text: str, model: str) -> int:
        # Heuristic — avoids shipping a tokenizer. ~4 chars/token.
        return max(1, len(text) // 4)

    async def list_models(self) -> list[ModelInfo]:
        url = f"{self._base_url}/models"
        client = self._client or self._new_client()
        try:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._client is None:
                await client.aclose()
        out: list[ModelInfo] = []
        for row in data.get("data", []) or []:
            mid = row.get("id")
            if not mid:
                continue
            out.append(ModelInfo(id=mid, provider=self.name, display_name=mid))
        return out

    async def health(self) -> HealthStatus:
        url = f"{self._base_url}/models"
        client = self._client or self._new_client()
        started = time.monotonic()
        try:
            resp = await client.get(url, headers=self._headers())
            ok = 200 <= resp.status_code < 300
            latency = (time.monotonic() - started) * 1000
            return HealthStatus(
                healthy=ok,
                latency_ms=round(latency, 2),
                detail=None if ok else f"http {resp.status_code}",
            )
        except httpx.HTTPError as exc:
            return HealthStatus(healthy=False, detail=f"{type(exc).__name__}: {exc}")
        finally:
            if self._client is None:
                await client.aclose()


# ── module-level translation helpers ────────────────────────────────────────


def _message_to_openai(m: Message) -> dict[str, Any]:
    """Canonical :class:`Message` → OpenAI message dict.

    Text-only messages collapse to a string ``content`` (OpenAI's common
    shape). Mixed/image content uses the content-parts array. Tool results
    become ``role="tool"`` with a ``tool_call_id``.
    """
    # Tool-result blocks → OpenAI role="tool".
    tool_results = [b for b in m.content if getattr(b, "type", None) == "tool_result"]
    if tool_results:
        tr = tool_results[0]
        return {
            "role": "tool",
            "tool_call_id": tr.tool_use_id,  # type: ignore[union-attr]
            "content": tr.content,  # type: ignore[union-attr]
        }

    # Assistant tool_use blocks → OpenAI tool_calls.
    tool_uses = [b for b in m.content if getattr(b, "type", None) == "tool_use"]
    text_parts = [b for b in m.content if getattr(b, "type", None) == "text"]
    image_parts = [b for b in m.content if getattr(b, "type", None) == "image"]

    role = "assistant" if m.role == "assistant" else m.role
    if m.role == "tool":
        role = "user"  # safety: no tool_call_id available here

    if tool_uses:
        msg: dict[str, Any] = {"role": "assistant"}
        text = "".join(t.text for t in text_parts)  # type: ignore[union-attr]
        msg["content"] = text or None
        msg["tool_calls"] = [
            {
                "id": tu.id,  # type: ignore[union-attr]
                "type": "function",
                "function": {
                    "name": tu.name,  # type: ignore[union-attr]
                    "arguments": json.dumps(tu.input),  # type: ignore[union-attr]
                },
            }
            for tu in tool_uses
        ]
        return msg

    if image_parts:
        parts: list[dict[str, Any]] = []
        for t in text_parts:
            parts.append({"type": "text", "text": t.text})  # type: ignore[union-attr]
        for img in image_parts:
            assert isinstance(img, ImageBlock)
            if img.url:
                url = img.url
            else:
                url = f"data:{img.media_type};base64,{img.data_base64}"
            parts.append({"type": "image_url", "image_url": {"url": url}})
        return {"role": role, "content": parts}

    text = "".join(t.text for t in text_parts)  # type: ignore[union-attr]
    out: dict[str, Any] = {"role": role, "content": text}
    if m.name:
        out["name"] = m.name
    return out


def _tool_choice_to_openai(tc: Any) -> Any:
    mode = getattr(tc, "mode", "auto")
    if mode == "none":
        return "none"
    if mode == "required":
        return "required"
    if mode == "tool" and getattr(tc, "tool_name", None):
        return {"type": "function", "function": {"name": tc.tool_name}}
    return "auto"


def _response_format_to_openai(rf: Any) -> dict[str, Any]:
    kind = getattr(rf, "kind", "text")
    if kind == "json_object":
        return {"type": "json_object"}
    if kind == "json_schema" and getattr(rf, "json_schema", None):
        return {
            "type": "json_schema",
            "json_schema": {
                "name": getattr(rf, "schema_name", None) or "response",
                "schema": rf.json_schema,
                "strict": bool(getattr(rf, "strict", False)),
            },
        }
    return {"type": "text"}


def _safe_json_args(raw: str | dict) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _response_from_openai(data: dict[str, Any], *, default_model: str) -> LLMResponse:
    """OpenAI ``chat.completion`` dict → canonical :class:`LLMResponse`."""
    choices = data.get("choices") or [{}]
    choice = choices[0]
    msg = choice.get("message") or {}

    content: list[Any] = []
    text = msg.get("content")
    if text:
        content.append(TextBlock(text=str(text)))

    tool_calls: list[ToolCall] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        tool_calls.append(
            ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=_safe_json_args(fn.get("arguments", "")),
            )
        )

    usage_raw = data.get("usage") or {}
    cached = (usage_raw.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    reasoning = (usage_raw.get("completion_tokens_details") or {}).get(
        "reasoning_tokens", 0
    )
    usage = Usage(
        input_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
        output_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
        cache_read_tokens=int(cached or 0),
        reasoning_tokens=int(reasoning or 0),
        total_tokens=int(usage_raw.get("total_tokens", 0) or 0),
    )

    return LLMResponse(
        id=data.get("id", ""),
        model_used=data.get("model", default_model),
        provider="openai",
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        stop_reason=_stop_from_finish(choice.get("finish_reason")),  # type: ignore[arg-type]
        raw=data,
    )


def _stream_chunks_from_openai(
    chunk: dict[str, Any], tool_buf: dict[int, dict[str, Any]]
) -> list[StreamChunk]:
    """One OpenAI ``chat.completion.chunk`` → canonical stream chunks.

    Tool-call argument fragments accumulate into ``tool_buf`` (flushed by the
    caller at stream end). Text deltas surface immediately. The terminal
    usage frame (``stream_options.include_usage``) becomes a UsageChunk.
    """
    out: list[StreamChunk] = []

    for ch in chunk.get("choices") or []:
        delta = ch.get("delta") or {}
        text = delta.get("content")
        if text:
            out.append(StreamChunk(root=TextDelta(text=text)))
        for tc in delta.get("tool_calls") or []:
            tindex = tc.get("index", 0)
            buf = tool_buf.setdefault(tindex, {"id": "", "name": "", "arguments": ""})
            if tc.get("id"):
                buf["id"] = tc["id"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                buf["name"] = fn["name"]
            if fn.get("arguments"):
                buf["arguments"] += fn["arguments"]

    usage_raw = chunk.get("usage")
    if usage_raw:
        cached = (usage_raw.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        reasoning = (usage_raw.get("completion_tokens_details") or {}).get(
            "reasoning_tokens", 0
        )
        out.append(
            StreamChunk(
                root=UsageChunk(
                    input_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
                    output_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
                    cache_read_tokens=int(cached or 0),
                    reasoning_tokens=int(reasoning or 0),
                )
            )
        )

    return out


__all__ = ["OpenAIProvider", "DEFAULT_BASE_URL"]
