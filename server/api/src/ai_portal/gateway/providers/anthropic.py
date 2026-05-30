"""Anthropic HTTP adapter — canonical :class:`LLMProvider` over raw httpx.

Wraps the Anthropic Messages API directly (no SDK) so calls are mockable with
``respx`` and the gateway keeps one code path. Verified against the Messages
API: ``anthropic-version: 2023-06-01`` header, ``/v1/messages`` body with
``model`` / ``max_tokens`` / ``messages`` / ``system`` / ``tools`` /
``thinking``, usage fields ``input_tokens`` / ``output_tokens`` /
``cache_creation_input_tokens`` / ``cache_read_input_tokens``, stop reasons
``end_turn`` / ``max_tokens`` / ``stop_sequence`` / ``tool_use``, and SSE
events ``message_start`` / ``content_block_start`` / ``content_block_delta``
(``text_delta`` / ``thinking_delta`` / ``input_json_delta``) /
``content_block_stop`` / ``message_delta`` / ``message_stop``.

Implements:

- :meth:`complete_canonical` → ``POST /v1/messages``
- :meth:`stream_canonical`   → ``POST /v1/messages`` (``stream=true`` SSE)
- :meth:`embed`              → raises (Anthropic ships no embeddings API)
- :meth:`count_tokens`       → ``POST /v1/messages/count_tokens`` cached fallback heuristic
- :meth:`list_models`        → ``GET /v1/models``
- :meth:`health`             → ``GET /v1/models`` probe

Secrets never appear in logs. The key lives only in the ``x-api-key`` header.
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
    IterationComplete,
    LLMRequest,
    LLMResponse,
    Message,
    ModelInfo,
    ProviderError,
    StreamChunk,
    TextBlock,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    ToolCallRequest,
    Usage,
    UsageChunk,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

# Anthropic stop_reason → canonical stop_reason.
_STOP_MAP: dict[str, str] = {
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
    "stop_sequence": "stop_sequence",
    "tool_use": "tool_use",
    "pause_turn": "end_turn",
    "refusal": "content_filter",
}


def _stop(reason: str | None) -> str:
    return _STOP_MAP.get(reason or "", "end_turn")


class AnthropicProvider:
    """Anthropic Messages provider speaking the canonical gateway protocol."""

    name: str = "anthropic"
    capabilities: set[Capability] = {
        "chat",
        "streaming",
        "tools",
        "vision",
        "thinking",
        "cache",
        "parallel_tools",
        "pdf",
    }

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        name: str = "anthropic",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicProvider requires a non-empty api_key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.name = name
        self._client = client

    # ── http plumbing ──────────────────────────────────────────────────────

    def _headers(self, *, extra_beta: str | None = None) -> dict[str, str]:
        h = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        if extra_beta:
            h["anthropic-beta"] = extra_beta
        return h

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=_TIMEOUT)

    # ── request translation ────────────────────────────────────────────────

    def _build_body(self, req: LLMRequest, *, stream: bool) -> dict[str, Any]:
        system_blocks, turns = _split_system(req.messages)
        body: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens or _DEFAULT_MAX_TOKENS,
            "messages": turns,
            "stream": stream,
        }
        if system_blocks:
            body["system"] = system_blocks
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.top_p is not None:
            body["top_p"] = req.top_p
        if req.stop:
            body["stop_sequences"] = req.stop
        if req.metadata.get("anthropic_user_id") or req.user:
            body["metadata"] = {
                "user_id": req.metadata.get("anthropic_user_id") or req.user
            }
        if req.tools:
            body["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema or {"type": "object"},
                }
                for t in req.tools
            ]
        if req.tool_choice is not None:
            tc = _tool_choice_to_anthropic(req.tool_choice)
            if tc is not None:
                body["tool_choice"] = tc
        if req.thinking is not None and req.thinking.enabled:
            body["thinking"] = {
                "type": "enabled",
                "budget_tokens": req.thinking.budget_tokens or 8000,
            }
        return body

    # ── completion ─────────────────────────────────────────────────────────

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        body = self._build_body(req, stream=False)
        url = f"{self._base_url}/messages"
        client = self._client or self._new_client()
        try:
            resp = await client.post(url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._client is None:
                await client.aclose()
        return _response_from_anthropic(data, default_model=req.model)

    async def stream_canonical(
        self, req: LLMRequest
    ) -> AsyncIterator[StreamChunk]:
        body = self._build_body(req, stream=True)
        url = f"{self._base_url}/messages"
        client = self._client or self._new_client()

        # Per-content-block accumulation for tool_use args.
        block_types: dict[int, str] = {}
        tool_blocks: dict[int, dict[str, Any]] = {}
        usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        stop_reason: str | None = None
        cur_event: str | None = None
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
                    line = line.rstrip("\r")
                    if line.startswith("event:"):
                        cur_event = line[len("event:") :].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:") :].strip()
                    if not raw:
                        continue
                    try:
                        ev = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    etype = ev.get("type") or cur_event
                    for sc in _handle_stream_event(
                        etype, ev, block_types, tool_blocks, usage
                    ):
                        yield sc
                    if etype == "message_delta":
                        sr = (ev.get("delta") or {}).get("stop_reason")
                        if sr:
                            stop_reason = sr
        except httpx.HTTPError as exc:
            yield StreamChunk(
                root=ProviderError(code=type(exc).__name__, message=str(exc))
            )
            return
        finally:
            if self._client is None:
                await client.aclose()

        # Flush completed tool_use blocks.
        for tb in tool_blocks.values():
            if tb.get("name"):
                yield StreamChunk(
                    root=ToolCallRequest(
                        call_id=tb.get("id", ""),
                        tool_name=tb["name"],
                        arguments=_safe_json_args(tb.get("partial_json", "")),
                    )
                )
        yield StreamChunk(
            root=UsageChunk(
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                cache_read_tokens=usage["cache_read"],
                cache_write_tokens=usage["cache_write"],
            )
        )
        yield StreamChunk(
            root=IterationComplete(stop_reason=_stop(stop_reason))  # type: ignore[arg-type]
        )

    # ── embeddings ─────────────────────────────────────────────────────────

    async def embed(self, texts: list[str], model: str) -> Embeddings:
        raise NotImplementedError(
            "Anthropic does not provide an embeddings API — route embeddings "
            "to an embeddings-capable provider (openai/voyage/cohere)."
        )

    # ── introspection ──────────────────────────────────────────────────────

    def count_tokens(self, text: str, model: str) -> int:
        # Local heuristic — the network count_tokens endpoint is exposed via
        # the compat surface; internal callers use this cheap estimate.
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
            out.append(
                ModelInfo(
                    id=mid,
                    provider=self.name,
                    display_name=row.get("display_name") or mid,
                )
            )
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


def _split_system(
    messages: list[Message],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split canonical messages into (system_blocks, turn_dicts).

    Anthropic takes the system prompt as a top-level ``system`` field, not a
    message. Consecutive same-role turns are merged (Anthropic requires
    alternation). ``cache_control`` on a system :class:`TextBlock` propagates.
    """
    system_blocks: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []

    for m in messages:
        if m.role == "system":
            for b in m.content:
                if getattr(b, "type", None) == "text":
                    block: dict[str, Any] = {"type": "text", "text": b.text}  # type: ignore[union-attr]
                    cc = getattr(b, "cache_control", None)
                    if cc is not None:
                        ttl = getattr(cc, "ttl", "5m")
                        block["cache_control"] = (
                            {"type": "ephemeral", "ttl": "1h"}
                            if ttl == "1h"
                            else {"type": "ephemeral"}
                        )
                    system_blocks.append(block)
            continue

        role = "assistant" if m.role == "assistant" else "user"
        content = _content_to_anthropic(m)
        if turns and turns[-1]["role"] == role:
            _merge_turn(turns[-1], content)
        else:
            turns.append({"role": role, "content": content})

    return system_blocks, turns


def _content_to_anthropic(m: Message) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in m.content:
        btype = getattr(b, "type", None)
        if btype == "text":
            out.append({"type": "text", "text": b.text})  # type: ignore[union-attr]
        elif btype == "image":
            if b.url:  # type: ignore[union-attr]
                out.append(
                    {
                        "type": "image",
                        "source": {"type": "url", "url": b.url},  # type: ignore[union-attr]
                    }
                )
            else:
                out.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": b.media_type,  # type: ignore[union-attr]
                            "data": b.data_base64,  # type: ignore[union-attr]
                        },
                    }
                )
        elif btype == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "id": b.id,  # type: ignore[union-attr]
                    "name": b.name,  # type: ignore[union-attr]
                    "input": b.input,  # type: ignore[union-attr]
                }
            )
        elif btype == "tool_result":
            out.append(
                {
                    "type": "tool_result",
                    "tool_use_id": b.tool_use_id,  # type: ignore[union-attr]
                    "content": b.content,  # type: ignore[union-attr]
                    "is_error": b.is_error,  # type: ignore[union-attr]
                }
            )
    if not out:
        out.append({"type": "text", "text": ""})
    return out


def _merge_turn(turn: dict[str, Any], extra: list[dict[str, Any]]) -> None:
    if isinstance(turn["content"], list):
        turn["content"].extend(extra)
    else:
        turn["content"] = [{"type": "text", "text": turn["content"]}, *extra]


def _tool_choice_to_anthropic(tc: Any) -> dict[str, Any] | None:
    mode = getattr(tc, "mode", "auto")
    if mode == "auto":
        return {"type": "auto"}
    if mode == "required":
        return {"type": "any"}
    if mode == "none":
        return None  # Anthropic: omit tools / no choice — caller drops tools
    if mode == "tool" and getattr(tc, "tool_name", None):
        return {"type": "tool", "name": tc.tool_name}
    return {"type": "auto"}


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


def _usage_from(raw: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=int(raw.get("input_tokens", 0) or 0),
        output_tokens=int(raw.get("output_tokens", 0) or 0),
        cache_read_tokens=int(raw.get("cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(raw.get("cache_creation_input_tokens", 0) or 0),
    )


def _response_from_anthropic(
    data: dict[str, Any], *, default_model: str
) -> LLMResponse:
    """Anthropic Messages response → canonical :class:`LLMResponse`."""
    content: list[Any] = []
    tool_calls: list[ToolCall] = []
    for block in data.get("content") or []:
        btype = block.get("type")
        if btype == "text":
            content.append(TextBlock(text=block.get("text", "")))
        elif btype == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=block.get("input", {}) or {},
                )
            )

    return LLMResponse(
        id=data.get("id", ""),
        model_used=data.get("model", default_model),
        provider="anthropic",
        content=content,
        tool_calls=tool_calls,
        usage=_usage_from(data.get("usage") or {}),
        stop_reason=_stop(data.get("stop_reason")),  # type: ignore[arg-type]
        raw=data,
    )


def _handle_stream_event(
    etype: str | None,
    ev: dict[str, Any],
    block_types: dict[int, str],
    tool_blocks: dict[int, dict[str, Any]],
    usage: dict[str, int],
) -> list[StreamChunk]:
    """Translate one Anthropic SSE event into canonical chunks.

    Mutates ``block_types`` / ``tool_blocks`` / ``usage`` accumulators in
    place; tool_use blocks are flushed by the caller at stream end.
    """
    out: list[StreamChunk] = []

    if etype == "message_start":
        u = (ev.get("message") or {}).get("usage") or {}
        usage["input"] += int(u.get("input_tokens", 0) or 0)
        usage["cache_read"] += int(u.get("cache_read_input_tokens", 0) or 0)
        usage["cache_write"] += int(u.get("cache_creation_input_tokens", 0) or 0)

    elif etype == "content_block_start":
        idx = ev.get("index", 0)
        block = ev.get("content_block") or {}
        btype = block.get("type", "")
        block_types[idx] = btype
        if btype == "tool_use":
            tool_blocks[idx] = {
                "id": block.get("id", ""),
                "name": block.get("name", ""),
                "partial_json": "",
            }

    elif etype == "content_block_delta":
        idx = ev.get("index", 0)
        delta = ev.get("delta") or {}
        dtype = delta.get("type")
        if dtype == "text_delta":
            txt = delta.get("text", "")
            if txt:
                out.append(StreamChunk(root=TextDelta(text=txt)))
        elif dtype == "thinking_delta":
            think = delta.get("thinking", "")
            if think:
                out.append(StreamChunk(root=ThinkingDelta(text=think)))
        elif dtype == "input_json_delta":
            tb = tool_blocks.get(idx)
            if tb is not None:
                tb["partial_json"] += delta.get("partial_json", "") or ""

    elif etype == "message_delta":
        u = ev.get("usage") or {}
        usage["output"] += int(u.get("output_tokens", 0) or 0)

    return out


__all__ = ["AnthropicProvider", "DEFAULT_BASE_URL", "ANTHROPIC_VERSION"]
