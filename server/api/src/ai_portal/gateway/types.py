"""Canonical request/response types for the gateway.

These types are **vendor-neutral**. Every provider-compatible surface
(OpenAI, Anthropic, Bedrock, …) translates incoming wire formats into these
shapes, and provider adapters translate them back out to the vendor SDK
they wrap.

All shapes are :class:`pydantic.BaseModel` so they round-trip via JSON
without losing fidelity (matters for trace persistence + replay).

Discriminated unions:

- :class:`ContentBlock` — ``text`` | ``image`` | ``tool_use`` | ``tool_result``
- :class:`StreamChunk`  — ``text_delta`` | ``thinking_delta`` |
  ``tool_call_request`` | ``server_tool_use`` | ``citation`` | ``usage`` |
  ``iteration_complete`` | ``provider_error``
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


# ── content blocks (multimodal message body) ────────────────────────────────


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextBlock(_Frozen):
    type: Literal["text"] = "text"
    text: str
    # anthropic-style cache marker; providers that don't support it ignore.
    cache_control: CacheHint | None = None


class ImageBlock(_Frozen):
    type: Literal["image"] = "image"
    # one of these is set; readers should prefer ``url`` when available.
    url: str | None = None
    data_base64: str | None = None
    media_type: str = "image/png"


class ToolUseBlock(_Frozen):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(_Frozen):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool = False


ContentBlockUnion = Annotated[
    TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock,
    Field(discriminator="type"),
]


class ContentBlock(RootModel[ContentBlockUnion]):
    """Discriminated wrapper around the content-block union.

    Most call sites pass the underlying block subclass directly; this wrapper
    exists so JSON payloads in traces / replays can be parsed back.
    """

    @property
    def kind(self) -> str:
        return self.root.type


# ── tools / function calling ────────────────────────────────────────────────


class ToolDef(_Frozen):
    """Generic function tool definition.

    Native server-side tools (Anthropic ``web_search_20260209``, Gemini
    grounding) are not modelled here — providers consume their own raw
    descriptors via :attr:`LLMRequest.metadata`.
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolChoice(_Frozen):
    """How the model should choose tools.

    Wire shapes:

    - ``mode="auto"`` — model decides
    - ``mode="none"`` — disable tool use
    - ``mode="required"`` — must call a tool
    - ``mode="tool"``  — must call ``tool_name``
    """

    mode: Literal["auto", "none", "required", "tool"] = "auto"
    tool_name: str | None = None


class ToolCall(_Frozen):
    """A resolved tool call returned by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


# ── response format / cache hints / thinking ────────────────────────────────


class ResponseFormat(_Frozen):
    """Controls structured-output mode.

    - ``kind="text"`` (default) — no constraint
    - ``kind="json_object"`` — must be valid JSON
    - ``kind="json_schema"`` — JSON matching :attr:`schema`
    """

    kind: Literal["text", "json_object", "json_schema"] = "text"
    schema_name: str | None = None
    json_schema: dict[str, Any] | None = None
    strict: bool = False


class CacheHint(_Frozen):
    """Per-segment cache hint (Anthropic prompt cache).

    - ``ttl="5m"`` — ephemeral 5-min tier
    - ``ttl="1h"`` — 1-hour tier
    """

    ttl: Literal["5m", "1h"] = "5m"


class ThinkingConfig(_Frozen):
    """Extended-thinking budget."""

    enabled: bool = False
    budget_tokens: int = 0


# ── messages ────────────────────────────────────────────────────────────────


class Message(_Frozen):
    role: Literal["system", "user", "assistant", "tool"]
    content: list[ContentBlockUnion] = Field(default_factory=list)
    name: str | None = None  # optional speaker name (OpenAI compat)


# ── capabilities + model info + health ──────────────────────────────────────


Capability = Literal[
    "chat",
    "streaming",
    "tools",
    "vision",
    "thinking",
    "cache",
    "json_mode",
    "json_schema",
    "embeddings",
    "rerank",
    "moderation",
    "web_search",
    "parallel_tools",
    "pdf",
]


class ModelInfo(_Frozen):
    """Snapshot of a single concrete model from a provider."""

    id: str
    provider: str
    display_name: str = ""
    capabilities: list[Capability] = Field(default_factory=list)
    context_window: int | None = None
    max_output_tokens: int | None = None
    price_input_per_1k_cents: float | None = None
    price_output_per_1k_cents: float | None = None
    price_cache_read_per_1k_cents: float | None = None
    deprecated_at: str | None = None


class HealthStatus(_Frozen):
    healthy: bool
    latency_ms: float | None = None
    detail: str | None = None


# ── request + response ──────────────────────────────────────────────────────


class LLMRequest(_Frozen):
    """Canonical, vendor-neutral request.

    ``model`` may be a virtual alias (resolved by routing) or a concrete id.
    ``metadata`` is a free-form bag for native pass-through (Anthropic
    ``anthropic-beta`` flags, OpenAI ``response_format`` raw payloads, …).
    """

    model: str
    messages: list[Message]
    tools: list[ToolDef] | None = None
    tool_choice: ToolChoice | None = None
    response_format: ResponseFormat | None = None
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    cache_hints: list[CacheHint] | None = None
    thinking: ThinkingConfig | None = None
    user: str | None = None  # actor id surfaced to provider for abuse signals


class Usage(_Frozen):
    """Token + cost accounting for one call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0  # may be left 0 when caller computes from parts


class LLMResponse(_Frozen):
    """Canonical, vendor-neutral non-streaming response."""

    id: str
    model_used: str
    provider: str
    content: list[ContentBlockUnion] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    stop_reason: Literal[
        "end_turn", "tool_use", "max_tokens", "stop_sequence", "content_filter", "unknown"
    ] = "end_turn"
    raw: dict[str, Any] = Field(default_factory=dict)


# ── stream chunks ───────────────────────────────────────────────────────────


class TextDelta(_Frozen):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ThinkingDelta(_Frozen):
    type: Literal["thinking_delta"] = "thinking_delta"
    text: str


class ToolCallRequest(_Frozen):
    type: Literal["tool_call_request"] = "tool_call_request"
    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ServerToolUse(_Frozen):
    type: Literal["server_tool_use"] = "server_tool_use"
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)


class Citation(_Frozen):
    type: Literal["citation"] = "citation"
    url: str
    title: str | None = None
    snippet: str | None = None


class UsageChunk(_Frozen):
    type: Literal["usage"] = "usage"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0


class IterationComplete(_Frozen):
    type: Literal["iteration_complete"] = "iteration_complete"
    stop_reason: Literal[
        "end_turn", "tool_use", "max_tokens", "stop_sequence", "content_filter", "unknown"
    ]


class ProviderError(_Frozen):
    type: Literal["provider_error"] = "provider_error"
    code: str
    message: str


StreamChunkUnion = Annotated[
    TextDelta
    | ThinkingDelta
    | ToolCallRequest
    | ServerToolUse
    | Citation
    | UsageChunk
    | IterationComplete
    | ProviderError,
    Field(discriminator="type"),
]


class StreamChunk(RootModel[StreamChunkUnion]):
    """Discriminated wrapper around stream-chunk variants.

    Provider adapters that already emit a discriminated chunk type may pass
    instances of the inner type directly; this wrapper exists so persisted
    traces can be re-hydrated.
    """

    @property
    def kind(self) -> str:
        return self.root.type


# ── embeddings ──────────────────────────────────────────────────────────────


class Embeddings(_Frozen):
    """Result of an embeddings request."""

    model: str
    provider: str
    vectors: list[list[float]] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


# rebuild for forward refs (CacheHint inside TextBlock)
TextBlock.model_rebuild()
