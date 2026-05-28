"""Adapter that lifts legacy :class:`ChatProvider` implementations into the
canonical :class:`LLMProvider` shape used by the gateway.

The legacy methods (``complete``, ``stream_deltas_with_tools``) speak in
loose ``list[dict]`` messages + vendor-shaped dicts. The gateway speaks in
:class:`ai_portal.gateway.LLMRequest` / :class:`LLMResponse` / :class:`StreamChunk`.

Rather than rewriting every provider to reimplement the canonical entry
points from scratch, this mixin:

- translates :class:`LLMRequest` → ``list[dict]`` messages + tool dicts
- delegates to the existing legacy methods
- translates the result back into canonical types

Subclasses still need to set :attr:`name` + :attr:`capabilities` (the
LLMProvider declaration) and may override ``embed`` / ``count_tokens`` /
``list_models`` / ``health`` for richer behaviour. Defaults raise
``NotImplementedError`` for ``embed`` and return best-effort heuristics
for ``count_tokens`` / ``health``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from ai_portal.catalog.providers.events import ProviderStreamEvent
from ai_portal.gateway.types import (
    Capability,
    Citation,
    Embeddings,
    HealthStatus,
    ImageBlock,
    IterationComplete,
    LLMRequest,
    LLMResponse,
    Message,
    ModelInfo,
    ProviderError,
    ServerToolUse,
    StreamChunk,
    TextBlock,
    ThinkingDelta,
    ToolCall,
    ToolCallRequest,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UsageChunk,
)


# ── canonical → legacy ──────────────────────────────────────────────────────


def _content_to_legacy_text(blocks: list) -> str:
    """Flatten canonical content blocks into a plain string for the legacy
    chat surface (which only consumes ``{"role", "content": str}``).

    Tool-use / tool-result / image blocks are stringified in a stable way so
    nothing is silently dropped — provider-aware adapters can override.
    """
    parts: list[str] = []
    for block in blocks:
        # ``block`` here may be a TextBlock / ImageBlock / ... instance (when
        # the caller built the Message directly) or already a discriminated
        # dict (after round-tripping via JSON).
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, ImageBlock):
            parts.append(f"[image:{block.url or block.media_type}]")
        elif isinstance(block, ToolUseBlock):
            parts.append(f"[tool_use:{block.name}({json.dumps(block.input)})]")
        elif isinstance(block, ToolResultBlock):
            parts.append(block.content)
        elif isinstance(block, dict):
            t = block.get("type")
            if t == "text":
                parts.append(str(block.get("text", "")))
            elif t == "image":
                parts.append(f"[image:{block.get('url') or block.get('media_type')}]")
            elif t == "tool_use":
                parts.append(
                    f"[tool_use:{block.get('name')}({json.dumps(block.get('input') or {})})]"
                )
            elif t == "tool_result":
                parts.append(str(block.get("content", "")))
    return "".join(parts)


def request_to_legacy_messages(req: LLMRequest) -> list[dict[str, Any]]:
    """Translate canonical messages into the legacy dict format."""
    out: list[dict[str, Any]] = []
    for m in req.messages:
        # tool-use messages on the assistant side need a ``tool_calls`` shim
        # so the existing anthropic/gemini adapters can rebuild blocks.
        if m.role == "assistant":
            tool_calls: list[dict[str, Any]] = []
            text_parts: list[str] = []
            for block in m.content:
                if isinstance(block, ToolUseBlock):
                    tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    })
                elif isinstance(block, TextBlock):
                    text_parts.append(block.text)
                elif isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input") or {}),
                        },
                    })
                elif isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
            entry: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
            continue

        if m.role == "tool":
            # Tool result lives in a single ToolResultBlock per message.
            for block in m.content:
                if isinstance(block, ToolResultBlock):
                    out.append({
                        "role": "tool",
                        "content": block.content,
                        "tool_call_id": block.tool_use_id,
                    })
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    out.append({
                        "role": "tool",
                        "content": str(block.get("content", "")),
                        "tool_call_id": block.get("tool_use_id", ""),
                    })
            continue

        out.append({"role": m.role, "content": _content_to_legacy_text(m.content)})
    return out


def tools_to_legacy(req: LLMRequest) -> list[dict[str, Any]] | None:
    """Translate :class:`ToolDef`\\s into the legacy function-tool dict shape."""
    if not req.tools:
        return None
    out: list[dict[str, Any]] = []
    for t in req.tools:
        out.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema or {"type": "object", "properties": {}},
            },
        })
    return out


# ── legacy → canonical (streaming chunks) ───────────────────────────────────


_LEGACY_TO_STOP_REASON: dict[str, str] = {
    "end_turn": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "stop_sequence": "stop_sequence",
    "STOP": "end_turn",
    "MAX_TOKENS": "max_tokens",
    "TOOL": "tool_use",
    "FUNCTION": "tool_use",
    "SAFETY": "content_filter",
}


def _provider_event_to_chunks(ev: ProviderStreamEvent) -> list[StreamChunk]:
    """Translate one legacy :class:`ProviderStreamEvent` into canonical chunks."""
    root = ev.root
    t = root.type

    if t == "text_delta":
        return [StreamChunk(root={"type": "text_delta", "text": root.text})]
    if t == "thinking_delta":
        return [StreamChunk(root={"type": "thinking_delta", "text": root.text})]
    if t == "tool_call_request":
        return [StreamChunk(root={
            "type": "tool_call_request",
            "call_id": root.call_id,
            "tool_name": root.tool_name,
            "arguments": root.arguments,
        })]
    if t == "server_tool_use":
        return [StreamChunk(root={
            "type": "server_tool_use",
            "tool_name": root.tool_name,
            "input": root.input,
        })]
    if t == "citation":
        return [StreamChunk(root={
            "type": "citation",
            "url": root.url,
            "title": root.title,
            "snippet": root.snippet,
        })]
    if t == "usage":
        return [StreamChunk(root={
            "type": "usage",
            "input_tokens": root.input_tokens,
            "output_tokens": root.output_tokens,
            "cache_read_tokens": root.cached_input_tokens,
            "cache_write_tokens": root.cache_creation_input_tokens,
            "reasoning_tokens": root.reasoning_tokens or 0,
        })]
    if t == "iteration_complete":
        return [StreamChunk(root={
            "type": "iteration_complete",
            "stop_reason": root.stop_reason if root.stop_reason in {
                "end_turn", "tool_use", "max_tokens", "stop_sequence",
                "content_filter", "unknown",
            } else "unknown",
        })]
    if t == "provider_error":
        return [StreamChunk(root={
            "type": "provider_error",
            "code": root.code,
            "message": root.message,
        })]
    return []


# ── mixin ───────────────────────────────────────────────────────────────────


class CanonicalProviderMixin:
    """Provides default canonical-protocol methods on top of a legacy provider.

    Concrete providers must still set ``name`` + ``capabilities`` as class
    attributes. They may override any method here for richer behaviour.
    """

    # subclasses override
    name: str = "unknown"
    capabilities: set[Capability] = set()

    # ── canonical complete (translates LLMRequest → legacy + back) ──────────

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        """Canonical non-streaming completion.

        Translates the canonical request into the legacy ``list[dict]``
        message format, calls the subclass's existing ``complete()`` method,
        and wraps the result back into :class:`LLMResponse`.

        Subclasses with native cancellation / async paths can override.
        """
        legacy_messages = request_to_legacy_messages(req)
        # legacy .complete is sync — call inline. The gateway service layer
        # will offload to a thread pool when wiring through fastapi.
        raw = self._invoke_legacy_complete(legacy_messages, req.model)
        choices = raw.get("choices", [])
        text = ""
        if choices:
            msg = choices[0].get("message") or {}
            text = str(msg.get("content") or "")
        return LLMResponse(
            id=f"resp_{uuid.uuid4().hex[:16]}",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text=text)],
            tool_calls=[],
            usage=Usage(),
            stop_reason="end_turn",
            raw=raw,
        )

    def _invoke_legacy_complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None,
    ) -> dict[str, Any]:
        """Call the legacy ``complete`` method on the concrete provider.

        Concrete provider classes define a sync ``complete(messages, *, model)``
        method (the legacy :class:`ChatProvider` contract). We invoke it here
        from the canonical path. Subclasses that override ``complete`` for
        the canonical signature must also override this hook.
        """
        return self.complete(messages, model=model)  # type: ignore[misc]

    # ── canonical stream (translates LLMRequest → legacy events → chunks) ───

    async def stream_canonical(
        self,
        req: LLMRequest,
    ) -> AsyncIterator[StreamChunk]:
        """Canonical async stream."""
        legacy_messages = request_to_legacy_messages(req)
        legacy_tools = tools_to_legacy(req)
        try:
            async for ev in self._invoke_legacy_stream(
                messages=legacy_messages,
                model=req.model,
                tools=legacy_tools,
            ):
                for chunk in _provider_event_to_chunks(ev):
                    yield chunk
        except Exception as exc:  # pragma: no cover — protocol guarantees this path
            yield StreamChunk(root={
                "type": "provider_error",
                "code": type(exc).__name__,
                "message": str(exc),
            })

    async def _invoke_legacy_stream(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Call the legacy async ``stream`` method on the concrete provider."""
        async for ev in self.stream(  # type: ignore[misc]
            messages=messages,
            model=model,
            settings={},
            tools=tools,
        ):
            yield ev

    # ── canonical embed ─────────────────────────────────────────────────────

    async def embed(self, texts: list[str], model: str) -> Embeddings:
        raise NotImplementedError(
            f"{type(self).__name__} does not support embeddings"
        )

    # ── canonical count_tokens (heuristic default) ──────────────────────────

    def count_tokens(self, text: str, model: str) -> int:
        # cheap default: ~4 chars per token, never less than 1.
        if not text:
            return 0
        return max(1, len(text) // 4)

    # ── canonical list_models ───────────────────────────────────────────────

    async def list_models(self) -> list[ModelInfo]:
        return []

    # ── canonical health (no network call by default) ───────────────────────

    async def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="default-passthrough")


__all__ = [
    "CanonicalProviderMixin",
    "request_to_legacy_messages",
    "tools_to_legacy",
]
