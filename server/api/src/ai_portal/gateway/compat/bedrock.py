"""Bedrock Converse-compatible HTTP surface.

Endpoints
---------

- ``POST /v1/converse`` — non-streaming completion
- ``POST /v1/converse-stream`` — streaming completion (AWS event-stream)

The router only **translates** between the Bedrock Converse wire format
and the canonical :class:`ai_portal.gateway.LLMRequest` /
:class:`LLMResponse`. The actual dispatch (provider selection, routing,
guardrails, traces) lives behind :func:`get_gateway_service` so it can
be overridden in tests and swapped out as later gateway phases land.

Bedrock Converse shape reference
--------------------------------

Request::

    {
      "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
      "messages": [
        {"role": "user", "content": [{"text": "..."}, {"image": {...}}, ...]}
      ],
      "system": [{"text": "..."}],
      "inferenceConfig": {"maxTokens", "temperature", "topP", "stopSequences"},
      "toolConfig": {"tools": [{"toolSpec": {...}}], "toolChoice": {...}}
    }

Response::

    {
      "output": {"message": {"role": "assistant", "content": [...]}},
      "stopReason": "end_turn" | "tool_use" | "max_tokens" | "stop_sequence",
      "usage": {"inputTokens", "outputTokens", "totalTokens"}
    }

Content block kinds (Bedrock):

- ``{"text": "..."}``
- ``{"image": {"format": "png|jpeg|gif|webp", "source": {"bytes": <b64>}}}``
- ``{"toolUse": {"toolUseId", "name", "input": {...}}}``
- ``{"toolResult": {"toolUseId", "content": [...], "status": "success|error"}}``

Streaming uses AWS event-stream framing. Real AWS clients consume the
binary protocol; for first-party + test consumers we emit a textual
variant tagged with ``application/vnd.amazon.eventstream`` containing
one event per delimited block::

    :event-type:messageStart
    {"role": "assistant"}

    :event-type:contentBlockDelta
    {"contentBlockIndex": 0, "delta": {"text": "Hel"}}

    ...

    :event-type:metadata
    {"usage": {...}}

This is enough for the gateway's tests and is trivially convertible
to the binary AWS framing in a downstream adapter if a real boto3
client is pointed at the gateway.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ai_portal.gateway.types import (
    ImageBlock,
    LLMRequest,
    LLMResponse,
    Message,
    ProviderError,
    StreamChunk,
    TextBlock,
    ToolCallRequest,
    ToolChoice,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
)

# ── gateway service protocol (DI-overridable) ────────────────────────────


class GatewayService(Protocol):
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


# ── inbound (Bedrock-shaped) request models ──────────────────────────────


class _BdModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


# Content blocks --------------------------------------------------------


class _BdTextBlock(_BdModel):
    text: str


class _BdImageSource(_BdModel):
    bytes: str | None = None  # base64 string


class _BdImageBody(_BdModel):
    format: Literal["png", "jpeg", "gif", "webp"] = "png"
    source: _BdImageSource


class _BdImageBlock(_BdModel):
    image: _BdImageBody


class _BdToolUseBody(_BdModel):
    toolUseId: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class _BdToolUseBlock(_BdModel):
    toolUse: _BdToolUseBody


class _BdToolResultContentItem(_BdModel):
    text: str | None = None
    json_: dict[str, Any] | None = Field(default=None, alias="json")


class _BdToolResultBody(_BdModel):
    toolUseId: str
    content: list[_BdToolResultContentItem] = Field(default_factory=list)
    status: Literal["success", "error"] = "success"


class _BdToolResultBlock(_BdModel):
    toolResult: _BdToolResultBody


_BdContent = _BdTextBlock | _BdImageBlock | _BdToolUseBlock | _BdToolResultBlock


class _BdMessage(_BdModel):
    role: Literal["user", "assistant"]
    content: list[_BdContent] = Field(default_factory=list)


# Tools -----------------------------------------------------------------


class _BdToolInputSchema(_BdModel):
    # Bedrock wraps the JSON schema in {"json": {...}}.
    json_: dict[str, Any] = Field(default_factory=dict, alias="json")


class _BdToolSpec(_BdModel):
    name: str
    description: str = ""
    inputSchema: _BdToolInputSchema = Field(default_factory=_BdToolInputSchema)


class _BdTool(_BdModel):
    toolSpec: _BdToolSpec


class _BdToolChoiceTool(_BdModel):
    name: str


class _BdToolChoice(_BdModel):
    auto: dict[str, Any] | None = None
    any: dict[str, Any] | None = None
    tool: _BdToolChoiceTool | None = None


class _BdToolConfig(_BdModel):
    tools: list[_BdTool] = Field(default_factory=list)
    toolChoice: _BdToolChoice | None = None


# Inference config ------------------------------------------------------


class _BdInferenceConfig(_BdModel):
    maxTokens: int | None = None
    temperature: float | None = None
    topP: float | None = None
    stopSequences: list[str] | None = None


class _BdConverseRequest(_BdModel):
    modelId: str
    messages: list[_BdMessage]
    system: list[_BdTextBlock] | None = None
    inferenceConfig: _BdInferenceConfig | None = None
    toolConfig: _BdToolConfig | None = None
    additionalModelRequestFields: dict[str, Any] | None = None


# ── translation: inbound → LLMRequest ────────────────────────────────────


def _content_block_to_canonical(c: _BdContent) -> Any | None:
    if isinstance(c, _BdTextBlock):
        return TextBlock(text=c.text)
    if isinstance(c, _BdImageBlock):
        body = c.image
        media = f"image/{body.format}"
        return ImageBlock(
            data_base64=body.source.bytes or "",
            media_type=media,
        )
    if isinstance(c, _BdToolUseBlock):
        tu = c.toolUse
        return ToolUseBlock(id=tu.toolUseId, name=tu.name, input=tu.input or {})
    if isinstance(c, _BdToolResultBlock):
        tr = c.toolResult
        # Flatten content list to a single string (canonical tool_result
        # carries content as str).
        parts: list[str] = []
        for item in tr.content:
            if item.text is not None:
                parts.append(item.text)
            elif item.json_ is not None:
                parts.append(json.dumps(item.json_, separators=(",", ":")))
        joined = "\n".join(parts)
        return ToolResultBlock(
            tool_use_id=tr.toolUseId,
            content=joined,
            is_error=(tr.status == "error"),
        )
    return None


def _translate_messages(messages: list[_BdMessage]) -> list[Message]:
    out: list[Message] = []
    for m in messages:
        blocks: list[Any] = []
        for c in m.content:
            block = _content_block_to_canonical(c)
            if block is not None:
                blocks.append(block)
        out.append(Message(role=m.role, content=blocks))
    return out


def _translate_system(system: list[_BdTextBlock] | None) -> Message | None:
    if not system:
        return None
    blocks = [TextBlock(text=s.text) for s in system if s.text]
    if not blocks:
        return None
    return Message(role="system", content=blocks)


def _translate_tools(cfg: _BdToolConfig | None) -> list[ToolDef] | None:
    if cfg is None or not cfg.tools:
        return None
    out: list[ToolDef] = []
    for t in cfg.tools:
        spec = t.toolSpec
        out.append(
            ToolDef(
                name=spec.name,
                description=spec.description or "",
                input_schema=spec.inputSchema.json_ or {},
            )
        )
    return out


def _translate_tool_choice(cfg: _BdToolConfig | None) -> ToolChoice | None:
    if cfg is None or cfg.toolChoice is None:
        return None
    tc = cfg.toolChoice
    if tc.tool is not None:
        return ToolChoice(mode="tool", tool_name=tc.tool.name)
    if tc.any is not None:
        return ToolChoice(mode="required")
    if tc.auto is not None:
        return ToolChoice(mode="auto")
    return ToolChoice(mode="auto")


def _request_to_llm(body: _BdConverseRequest, *, stream: bool) -> LLMRequest:
    messages: list[Message] = []
    sys = _translate_system(body.system)
    if sys is not None:
        messages.append(sys)
    messages.extend(_translate_messages(body.messages))

    inf = body.inferenceConfig or _BdInferenceConfig()

    metadata: dict[str, Any] = {}
    if body.additionalModelRequestFields:
        metadata["bedrock_additional_fields"] = dict(body.additionalModelRequestFields)

    return LLMRequest(
        model=body.modelId,
        messages=messages,
        tools=_translate_tools(body.toolConfig),
        tool_choice=_translate_tool_choice(body.toolConfig),
        stream=stream,
        max_tokens=inf.maxTokens,
        temperature=inf.temperature,
        top_p=inf.topP,
        stop=inf.stopSequences,
        metadata=metadata,
    )


# ── translation: LLMResponse → Bedrock wire ──────────────────────────────


def _content_block_to_wire(block: Any) -> dict[str, Any]:
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"text": getattr(block, "text", "")}
    if btype == "tool_use":
        return {
            "toolUse": {
                "toolUseId": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": getattr(block, "input", {}) or {},
            }
        }
    if btype == "tool_result":
        return {
            "toolResult": {
                "toolUseId": getattr(block, "tool_use_id", ""),
                "content": [{"text": getattr(block, "content", "")}],
                "status": "error" if getattr(block, "is_error", False) else "success",
            }
        }
    if btype == "image":
        media = getattr(block, "media_type", "image/png") or "image/png"
        fmt = media.split("/", 1)[1] if "/" in media else "png"
        return {
            "image": {
                "format": fmt,
                "source": {"bytes": getattr(block, "data_base64", "") or ""},
            }
        }
    return {"text": ""}


def _response_to_wire(resp: LLMResponse) -> dict[str, Any]:
    content = [_content_block_to_wire(b) for b in resp.content]
    usage = resp.usage
    total = usage.total_tokens or (usage.input_tokens + usage.output_tokens)
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": content,
            }
        },
        "stopReason": resp.stop_reason,
        "usage": {
            "inputTokens": usage.input_tokens,
            "outputTokens": usage.output_tokens,
            "totalTokens": total,
        },
    }


# ── streaming: canonical chunks → AWS event-stream (text framing) ────────


_STOP_REASONS = {
    "end_turn",
    "tool_use",
    "max_tokens",
    "stop_sequence",
    "content_filter",
}


def _aws_event(name: str, payload: dict[str, Any]) -> bytes:
    """Encode one event in the text variant of the AWS event-stream wire."""
    return (
        f":event-type:{name}\n{json.dumps(payload, separators=(',', ':'))}\n\n"
    ).encode()


def _chunk_kind(chunk: Any) -> str | None:
    if isinstance(chunk, StreamChunk):
        return chunk.root.type  # type: ignore[union-attr]
    return getattr(chunk, "type", None)


def _chunk_root(chunk: Any) -> Any:
    return chunk.root if isinstance(chunk, StreamChunk) else chunk


async def _to_bedrock_stream(
    chunks: AsyncIterator[Any],
) -> AsyncIterator[bytes]:
    """Translate canonical stream chunks to Bedrock Converse stream events."""
    started = False
    current_kind: Literal["text", "tool_use", None] = None
    block_index = -1

    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    cache_write = 0
    stop_reason: str = "end_turn"

    def _ensure_message_start() -> bytes:
        nonlocal started
        if started:
            return b""
        started = True
        return _aws_event("messageStart", {"role": "assistant"})

    def _close_current_block() -> bytes:
        nonlocal current_kind
        if current_kind is None:
            return b""
        out = _aws_event(
            "contentBlockStop",
            {"contentBlockIndex": block_index},
        )
        current_kind = None
        return out

    def _open_text_block() -> bytes:
        nonlocal current_kind, block_index
        block_index += 1
        current_kind = "text"
        return _aws_event(
            "contentBlockStart",
            {
                "contentBlockIndex": block_index,
                "start": {},
            },
        )

    def _open_tool_use_block(tc: ToolCallRequest) -> bytes:
        nonlocal current_kind, block_index
        block_index += 1
        current_kind = "tool_use"
        return _aws_event(
            "contentBlockStart",
            {
                "contentBlockIndex": block_index,
                "start": {
                    "toolUse": {
                        "toolUseId": tc.call_id,
                        "name": tc.tool_name,
                    }
                },
            },
        )

    try:
        async for raw in chunks:
            kind = _chunk_kind(raw)
            root = _chunk_root(raw)

            if kind == "text_delta":
                out = _ensure_message_start()
                if out:
                    yield out
                if current_kind != "text":
                    if current_kind is not None:
                        yield _close_current_block()
                    yield _open_text_block()
                yield _aws_event(
                    "contentBlockDelta",
                    {
                        "contentBlockIndex": block_index,
                        "delta": {"text": root.text},
                    },
                )

            elif kind == "tool_call_request":
                out = _ensure_message_start()
                if out:
                    yield out
                if current_kind is not None:
                    yield _close_current_block()
                yield _open_tool_use_block(root)
                # Emit full arguments as one inputJsonDelta — real Bedrock
                # streams partial JSON deltas, but downstream accumulators
                # treat full-blob deltas identically.
                yield _aws_event(
                    "contentBlockDelta",
                    {
                        "contentBlockIndex": block_index,
                        "delta": {
                            "toolUse": {
                                "input": json.dumps(
                                    root.arguments or {}, separators=(",", ":")
                                )
                            }
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
                        "message": root.message,
                        "code": root.code or "InternalServerException",
                    }
                else:
                    err_payload = {
                        "message": "unknown",
                        "code": "InternalServerException",
                    }
                yield _aws_event("internalServerException", err_payload)
                return

            # thinking_delta / citation / server_tool_use — pass for now;
            # Bedrock surfaces these in additionalModelResponseFields once
            # we wire native reasoning.

        # Stream ended cleanly.
        out = _ensure_message_start()
        if out:
            yield out
        if current_kind is not None:
            yield _close_current_block()
        yield _aws_event("messageStop", {"stopReason": stop_reason})
        total = input_tokens + output_tokens
        metadata: dict[str, Any] = {
            "usage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalTokens": total,
            }
        }
        if cache_read or cache_write:
            metadata["usage"]["cacheReadInputTokens"] = cache_read
            metadata["usage"]["cacheWriteInputTokens"] = cache_write
        yield _aws_event("metadata", metadata)

    except Exception as exc:  # pragma: no cover — defensive
        yield _aws_event(
            "internalServerException",
            {"message": str(exc), "code": type(exc).__name__},
        )


# ── router ───────────────────────────────────────────────────────────────


router = APIRouter(tags=["gateway-bedrock-compat"])


def _ensure_response_id(resp: LLMResponse) -> LLMResponse:
    """Bedrock responses don't carry an id; one is generated upstream."""
    if not resp.id:
        return resp.model_copy(update={"id": f"msg_{uuid.uuid4().hex[:24]}"})
    return resp


@router.post("/v1/converse")
async def post_converse(
    body: _BdConverseRequest,
    svc: GatewayService = Depends(get_gateway_service),
) -> Any:
    """Bedrock Converse non-streaming endpoint."""
    req = _request_to_llm(body, stream=False)
    resp = _ensure_response_id(await svc.complete(req))
    return JSONResponse(_response_to_wire(resp))


@router.post("/v1/converse-stream")
async def post_converse_stream(
    body: _BdConverseRequest,
    svc: GatewayService = Depends(get_gateway_service),
) -> Any:
    """Bedrock Converse streaming endpoint."""
    req = _request_to_llm(body, stream=True)

    async def _gen() -> AsyncIterator[bytes]:
        async for chunk in _to_bedrock_stream(svc.stream(req)):
            if chunk:
                yield chunk

    return StreamingResponse(
        _gen(),
        media_type="application/vnd.amazon.eventstream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = [
    "GatewayService",
    "get_gateway_service",
    "router",
]
