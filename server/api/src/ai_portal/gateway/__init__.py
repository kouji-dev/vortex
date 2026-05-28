"""Gateway module — unified, governed LLM control plane.

Public surface:

Canonical types
    :class:`LLMRequest`, :class:`LLMResponse`, :class:`Message`,
    :class:`ContentBlock`, :class:`ToolDef`/:class:`ToolChoice`/
    :class:`ToolCall`, :class:`ResponseFormat`, :class:`CacheHint`,
    :class:`ThinkingConfig`, :class:`Usage`, :class:`StreamChunk`,
    :class:`Embeddings`, :class:`ModelInfo`, :class:`HealthStatus`,
    :class:`Capability`.

Internal facade (Phase K)
    :func:`complete`, :func:`stream`, :func:`embed`, :func:`rerank`,
    :func:`count_tokens`, :func:`estimate_cost`. Composes routing + cache
    + guardrails + cost/budget + trace writer + audit + usage around the
    provider call. Other modules (chat, RAG, memories, workers) call
    these shortcuts; production startup wires the default facade via
    :func:`set_default_facade`.
"""
from __future__ import annotations

from ai_portal.gateway.facade import (
    Actor,
    FacadeConfig,
    GatewayFacade,
    complete,
    count_tokens,
    embed,
    estimate_cost,
    get_default_facade,
    rerank,
    set_default_facade,
    stream,
)
from ai_portal.gateway.types import (
    Capability,
    CacheHint,
    ContentBlock,
    Embeddings,
    HealthStatus,
    ImageBlock,
    LLMRequest,
    LLMResponse,
    Message,
    ModelInfo,
    ResponseFormat,
    StreamChunk,
    TextBlock,
    ThinkingConfig,
    ToolCall,
    ToolChoice,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
)

__all__ = [
    "Actor",
    "Capability",
    "CacheHint",
    "ContentBlock",
    "Embeddings",
    "FacadeConfig",
    "GatewayFacade",
    "HealthStatus",
    "ImageBlock",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "ModelInfo",
    "ResponseFormat",
    "StreamChunk",
    "TextBlock",
    "ThinkingConfig",
    "ToolCall",
    "ToolChoice",
    "ToolDef",
    "ToolResultBlock",
    "ToolUseBlock",
    "Usage",
    "complete",
    "count_tokens",
    "embed",
    "estimate_cost",
    "get_default_facade",
    "rerank",
    "set_default_facade",
    "stream",
]
