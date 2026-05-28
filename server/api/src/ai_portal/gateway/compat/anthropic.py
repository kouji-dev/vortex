"""Anthropic Messages-compatible HTTP surface.

Endpoints
---------

- ``POST /v1/messages`` — completion (streaming + non-streaming)
- ``POST /v1/messages/count_tokens`` — token estimate

The router only **translates** between Anthropic's wire format and the
canonical :class:`ai_portal.gateway.LLMRequest` / :class:`LLMResponse`.
The actual dispatch (provider selection, routing, guardrails, traces)
lives behind :func:`get_gateway_service` so it can be overridden in
tests and swapped out as later gateway phases land.

Anthropic header semantics
--------------------------

- ``anthropic-version`` → ``metadata["anthropic_version"]``
- ``anthropic-beta`` (comma-separated) → ``metadata["anthropic_beta"]`` (list)
- ``x-api-key`` / ``Authorization`` are validated by the API-key auth layer
  in front of this router; not consumed here.

Cache control
-------------

``cache_control`` markers on system text blocks or messages translate to
:class:`CacheHint` on the corresponding canonical block + appended to
:attr:`LLMRequest.cache_hints`. Provider adapters re-apply them when
calling Anthropic (`ephemeral` cache_control on the outgoing body).

Streaming SSE
-------------

Emits the standard Anthropic event sequence::

    event: message_start
    event: content_block_start (index=N, content_block=text|thinking|tool_use)
    event: content_block_delta (text_delta | thinking_delta | input_json_delta)
    event: content_block_stop
    ...repeat for additional blocks...
    event: message_delta  (stop_reason + usage)
    event: message_stop
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ai_portal.gateway.types import (
    CacheHint,
    ImageBlock,
    LLMRequest,
    LLMResponse,
    Message,
    ProviderError,
    StreamChunk,
    TextBlock,
    ThinkingConfig,
    ToolCallRequest,
    ToolChoice,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
)

# ── gateway service protocol (DI-overridable) ────────────────────────────


class GatewayService(Protocol):
    """The completion dispatcher used by every compat surface.

    Implementations land in later phases; for B3 the wire format and
    translation are what matter — tests inject a stub.
    """

    async def complete(self, req: LLMRequest) -> LLMResponse: ...
    async def stream(self, req: LLMRequest) -> AsyncIterator[Any]: ...
    def count_tokens(self, req: LLMRequest) -> int: ...


def get_gateway_service() -> GatewayService:
    """Default service hook — overridden in :mod:`main` once wired.

    Tests override via ``app.dependency_overrides``.
    """
    raise HTTPException(
        status_code=503,
        detail="gateway service not configured",
    )


# ── inbound (Anthropic-shaped) request models ────────────────────────────
# Use ``extra='ignore'`` so we tolerate the long tail of provider fields
# (metadata, stop_sequences, top_k, etc.) without losing them — they ride
# along in :attr:`LLMRequest.metadata`.


class _AntModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _AntCacheControl(_AntModel):
    type: Literal["ephemeral"] = "ephemeral"
    ttl: Literal["5m", "1h"] = "5m"


class _AntTextContent(_AntModel):
    type: Literal["text"]
    text: str
    cache_control: _AntCacheControl | None = None


class _AntImageSource(_AntModel):
    type: Literal["base64", "url"]
    media_type: str | None = None
    data: str | None = None
    url: str | None = None


class _AntImageContent(_AntModel):
    type: Literal["image"]
    source: _AntImageSource
    cache_control: _AntCacheControl | None = None


class _AntToolUseContent(_AntModel):
    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    cache_control: _AntCacheControl | None = None


class _AntToolResultContent(_AntModel):
    type: Literal["tool_result"]
    tool_use_id: str
    content: Any = ""
    is_error: bool = False
    cache_control: _AntCacheControl | None = None


class _AntThinkingContent(_AntModel):
    type: Literal["thinking"]
    thinking: str = ""
    signature: str | None = None


_AntContent = (
    _AntTextContent
    | _AntImageContent
    | _AntToolUseContent
    | _AntToolResultContent
    | _AntThinkingContent
)


class _AntMessage(_AntModel):
    role: Literal["user", "assistant"]
    content: str | list[_AntContent]


class _AntToolInputSchema(_AntModel):
    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class _AntTool(_AntModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    cache_control: _AntCacheControl | None = None


class _AntToolChoice(_AntModel):
    type: Literal["auto", "any", "tool", "none"]
    name: str | None = None


class _AntThinkingCfg(_AntModel):
    type: Literal["enabled", "disabled"]
    budget_tokens: int = 0


class _AntMessagesRequest(_AntModel):
    model: str
    max_tokens: int = 1024
    messages: list[_AntMessage]
    system: str | list[_AntTextContent] | None = None
    tools: list[_AntTool] | None = None
    tool_choice: _AntToolChoice | None = None
    thinking: _AntThinkingCfg | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    metadata: dict[str, Any] | None = None
    user: str | None = None


class _AntCountTokensRequest(_AntModel):
    model: str
    messages: list[_AntMessage]
    system: str | list[_AntTextContent] | None = None
    tools: list[_AntTool] | None = None


# ── translation: inbound → LLMRequest ────────────────────────────────────


def _to_cache_hint(cc: _AntCacheControl | None) -> CacheHint | None:
    if cc is None:
        return None
    return CacheHint(ttl=cc.ttl)


def _translate_content_blocks(
    content: str | list[_AntContent],
    *,
    cache_hints_sink: list[CacheHint],
) -> list[Any]:
    """Translate one message body to canonical content blocks.

    Any cache_control hint on inbound blocks is forwarded both to the
    block itself (where the type supports it — currently text) and to
    the request-level ``cache_hints`` sink so the router can act on it.
    """
    if isinstance(content, str):
        return [TextBlock(text=content)]

    blocks: list[Any] = []
    for c in content:
        if isinstance(c, _AntTextContent):
            hint = _to_cache_hint(c.cache_control)
            if hint is not None:
                cache_hints_sink.append(hint)
            blocks.append(TextBlock(text=c.text, cache_control=hint))
        elif isinstance(c, _AntImageContent):
            src = c.source
            blocks.append(
                ImageBlock(
                    url=src.url,
                    data_base64=src.data,
                    media_type=src.media_type or "image/png",
                )
            )
            if c.cache_control is not None:
                cache_hints_sink.append(_to_cache_hint(c.cache_control))
        elif isinstance(c, _AntToolUseContent):
            blocks.append(ToolUseBlock(id=c.id, name=c.name, input=c.input or {}))
            if c.cache_control is not None:
                cache_hints_sink.append(_to_cache_hint(c.cache_control))
        elif isinstance(c, _AntToolResultContent):
            # Anthropic permits content to be str or list[block]; coerce
            # to a flat string for the canonical shape (we don't lose
            # data — multimodal tool_result is rare and the canonical
            # representation is a simple string per the gateway types).
            payload = c.content
            if isinstance(payload, list):
                joined: list[str] = []
                for p in payload:
                    if isinstance(p, dict):
                        joined.append(str(p.get("text", "") or p.get("content", "")))
                    else:
                        joined.append(str(p))
                payload = "\n".join(s for s in joined if s)
            blocks.append(
                ToolResultBlock(
                    tool_use_id=c.tool_use_id,
                    content=str(payload) if payload is not None else "",
                    is_error=c.is_error,
                )
            )
            if c.cache_control is not None:
                cache_hints_sink.append(_to_cache_hint(c.cache_control))
        elif isinstance(c, _AntThinkingContent):
            # Inbound thinking blocks (from prior turns) are not part of
            # the canonical content union — drop. The model regenerates
            # thinking each turn anyway.
            continue
    return blocks


_TOOL_CHOICE_MAP: dict[str, str] = {
    "auto": "auto",
    "none": "none",
    "any": "required",
    "tool": "tool",
}


def _translate_tool_choice(tc: _AntToolChoice | None) -> ToolChoice | None:
    if tc is None:
        return None
    mode = _TOOL_CHOICE_MAP.get(tc.type, "auto")
    return ToolChoice(mode=mode, tool_name=tc.name)


def _translate_tools(tools: list[_AntTool] | None) -> list[ToolDef] | None:
    if not tools:
        return None
    return [
        ToolDef(
            name=t.name,
            description=t.description or "",
            input_schema=t.input_schema or {},
        )
        for t in tools
    ]


def _translate_thinking(t: _AntThinkingCfg | None) -> ThinkingConfig | None:
    if t is None:
        return None
    return ThinkingConfig(
        enabled=(t.type == "enabled"),
        budget_tokens=t.budget_tokens,
    )


def _translate_system(
    system: str | list[_AntTextContent] | None,
    *,
    cache_hints_sink: list[CacheHint],
) -> Message | None:
    if system is None:
        return None
    if isinstance(system, str):
        if not system:
            return None
        return Message(role="system", content=[TextBlock(text=system)])
    blocks: list[Any] = []
    for s in system:
        hint = _to_cache_hint(s.cache_control)
        if hint is not None:
            cache_hints_sink.append(hint)
        blocks.append(TextBlock(text=s.text, cache_control=hint))
    if not blocks:
        return None
    return Message(role="system", content=blocks)


def _build_metadata(
    *,
    anthropic_version: str | None,
    anthropic_beta: str | None,
    raw_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    md: dict[str, Any] = {}
    if raw_metadata:
        md.update(raw_metadata)
    if anthropic_version:
        md["anthropic_version"] = anthropic_version
    if anthropic_beta:
        md["anthropic_beta"] = [
            s.strip() for s in anthropic_beta.split(",") if s.strip()
        ]
    return md


def _request_to_llm(
    body: _AntMessagesRequest,
    *,
    anthropic_version: str | None,
    anthropic_beta: str | None,
) -> LLMRequest:
    cache_hints: list[CacheHint] = []

    messages: list[Message] = []
    sys = _translate_system(body.system, cache_hints_sink=cache_hints)
    if sys is not None:
        messages.append(sys)

    for m in body.messages:
        blocks = _translate_content_blocks(m.content, cache_hints_sink=cache_hints)
        messages.append(Message(role=m.role, content=blocks))

    return LLMRequest(
        model=body.model,
        messages=messages,
        tools=_translate_tools(body.tools),
        tool_choice=_translate_tool_choice(body.tool_choice),
        stream=body.stream,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        top_p=body.top_p,
        stop=body.stop_sequences,
        cache_hints=cache_hints or None,
        thinking=_translate_thinking(body.thinking),
        user=body.user,
        metadata=_build_metadata(
            anthropic_version=anthropic_version,
            anthropic_beta=anthropic_beta,
            raw_metadata=body.metadata,
        ),
    )


# ── translation: LLMResponse → Anthropic wire ────────────────────────────


def _content_block_to_wire(block: Any) -> dict[str, Any]:
    """Convert a canonical content block to its Anthropic wire shape."""
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": getattr(block, "id", ""),
            "name": getattr(block, "name", ""),
            "input": getattr(block, "input", {}) or {},
        }
    if btype == "image":
        # Echo image blocks back in source form (rare on response side).
        if getattr(block, "url", None):
            return {
                "type": "image",
                "source": {"type": "url", "url": block.url},
            }
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": getattr(block, "media_type", "image/png"),
                "data": getattr(block, "data_base64", ""),
            },
        }
    if btype == "tool_result":
        return {
            "type": "tool_result",
            "tool_use_id": getattr(block, "tool_use_id", ""),
            "content": getattr(block, "content", ""),
            "is_error": getattr(block, "is_error", False),
        }
    return {"type": str(btype or "unknown")}


def _response_to_wire(resp: LLMResponse) -> dict[str, Any]:
    return {
        "id": resp.id,
        "type": "message",
        "role": "assistant",
        "model": resp.model_used,
        "content": [_content_block_to_wire(b) for b in resp.content],
        "stop_reason": resp.stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "cache_creation_input_tokens": resp.usage.cache_write_tokens,
            "cache_read_input_tokens": resp.usage.cache_read_tokens,
        },
    }


# ── streaming: canonical chunks → Anthropic SSE events ───────────────────


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _chunk_kind(chunk: Any) -> str | None:
    """Return the underlying chunk type whether wrapped in StreamChunk or not."""
    if isinstance(chunk, StreamChunk):
        return chunk.root.type  # type: ignore[union-attr]
    return getattr(chunk, "type", None)


def _chunk_root(chunk: Any) -> Any:
    return chunk.root if isinstance(chunk, StreamChunk) else chunk


_STOP_REASONS = {
    "end_turn",
    "tool_use",
    "max_tokens",
    "stop_sequence",
    "content_filter",
}


async def _to_anthropic_sse(
    chunks: AsyncIterator[Any],
    *,
    model: str,
) -> AsyncIterator[str]:
    """Translate canonical stream chunks to Anthropic SSE events."""
    message_id = f"msg_{uuid.uuid4().hex[:24]}"
    started = False
    # Track the currently-open content block.
    current_kind: Literal["text", "thinking", "tool_use", None] = None
    block_index = -1

    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    cache_write = 0
    stop_reason: str = "end_turn"

    def _ensure_message_start() -> str:
        nonlocal started
        if started:
            return ""
        started = True
        return _sse(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                    },
                },
            },
        )

    def _close_current_block() -> str:
        nonlocal current_kind
        if current_kind is None:
            return ""
        out = _sse(
            "content_block_stop",
            {"type": "content_block_stop", "index": block_index},
        )
        current_kind = None
        return out

    def _open_text_block() -> str:
        nonlocal current_kind, block_index
        block_index += 1
        current_kind = "text"
        return _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": block_index,
                "content_block": {"type": "text", "text": ""},
            },
        )

    def _open_thinking_block() -> str:
        nonlocal current_kind, block_index
        block_index += 1
        current_kind = "thinking"
        return _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": block_index,
                "content_block": {"type": "thinking", "thinking": ""},
            },
        )

    def _open_tool_use_block(tc: ToolCallRequest) -> str:
        nonlocal current_kind, block_index
        block_index += 1
        current_kind = "tool_use"
        return _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": block_index,
                "content_block": {
                    "type": "tool_use",
                    "id": tc.call_id,
                    "name": tc.tool_name,
                    "input": {},
                },
            },
        )

    try:
        async for raw in chunks:
            kind = _chunk_kind(raw)
            root = _chunk_root(raw)

            if kind == "text_delta":
                yield _ensure_message_start()
                if current_kind != "text":
                    if current_kind is not None:
                        yield _close_current_block()
                    yield _open_text_block()
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {
                            "type": "text_delta",
                            "text": root.text,
                        },
                    },
                )

            elif kind == "thinking_delta":
                yield _ensure_message_start()
                if current_kind != "thinking":
                    if current_kind is not None:
                        yield _close_current_block()
                    yield _open_thinking_block()
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {
                            "type": "thinking_delta",
                            "thinking": root.text,
                        },
                    },
                )

            elif kind == "tool_call_request":
                yield _ensure_message_start()
                if current_kind is not None:
                    yield _close_current_block()
                yield _open_tool_use_block(root)
                # Emit the full arguments as one input_json_delta — most
                # canonical producers carry the args as a parsed dict;
                # downstream Anthropic SDKs accumulate partial_json into
                # the final tool input.
                yield _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": json.dumps(
                                root.arguments or {}, separators=(",", ":")
                            ),
                        },
                    },
                )

            elif kind == "usage":
                input_tokens += root.input_tokens or 0
                output_tokens += root.output_tokens or 0
                cache_read += root.cache_read_tokens or 0
                cache_write += root.cache_write_tokens or 0

            elif kind == "iteration_complete":
                sr = root.stop_reason
                if sr in _STOP_REASONS:
                    stop_reason = sr

            elif kind == "provider_error":
                if isinstance(root, ProviderError):
                    err_payload = {
                        "type": "error",
                        "error": {
                            "type": root.code or "api_error",
                            "message": root.message,
                        },
                    }
                else:
                    err_payload = {
                        "type": "error",
                        "error": {"type": "api_error", "message": "unknown"},
                    }
                yield _sse("error", err_payload)
                return

            # other chunk kinds (citation, server_tool_use) — pass for now;
            # added back as native Anthropic events when web search lands.

        # Stream ended cleanly.
        yield _ensure_message_start()
        if current_kind is not None:
            yield _close_current_block()
        yield _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": stop_reason,
                    "stop_sequence": None,
                },
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_creation_input_tokens": cache_write,
                    "cache_read_input_tokens": cache_read,
                },
            },
        )
        yield _sse("message_stop", {"type": "message_stop"})

    except Exception as exc:  # pragma: no cover — defensive
        yield _sse(
            "error",
            {
                "type": "error",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            },
        )


# ── router ───────────────────────────────────────────────────────────────

router = APIRouter(tags=["gateway-anthropic-compat"])


@router.post("/v1/messages")
async def post_messages(
    body: _AntMessagesRequest,
    request: Request,
    anthropic_version: str | None = Header(default=None, alias="anthropic-version"),
    anthropic_beta: str | None = Header(default=None, alias="anthropic-beta"),
    svc: GatewayService = Depends(get_gateway_service),
) -> Any:
    """Anthropic-compatible completion endpoint."""
    req = _request_to_llm(
        body,
        anthropic_version=anthropic_version,
        anthropic_beta=anthropic_beta,
    )

    if not body.stream:
        resp = await svc.complete(req)
        return JSONResponse(_response_to_wire(resp))

    async def _gen() -> AsyncIterator[str]:
        async for chunk in _to_anthropic_sse(svc.stream(req), model=body.model):
            if chunk:
                yield chunk

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/v1/messages/count_tokens")
async def post_count_tokens(
    body: _AntCountTokensRequest,
    anthropic_version: str | None = Header(default=None, alias="anthropic-version"),
    anthropic_beta: str | None = Header(default=None, alias="anthropic-beta"),
    svc: GatewayService = Depends(get_gateway_service),
) -> dict[str, int]:
    """Anthropic-compatible token-count endpoint."""
    # Reuse the same translator by promoting the count-tokens body to a
    # minimal messages request (max_tokens unused).
    full = _AntMessagesRequest(
        model=body.model,
        max_tokens=1,
        messages=body.messages,
        system=body.system,
        tools=body.tools,
    )
    req = _request_to_llm(
        full,
        anthropic_version=anthropic_version,
        anthropic_beta=anthropic_beta,
    )
    n = svc.count_tokens(req)
    return {"input_tokens": int(n)}


__all__ = [
    "GatewayService",
    "get_gateway_service",
    "router",
]
