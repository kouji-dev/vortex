"""Gateway module — unified, governed LLM control plane.

Public surface (canonical types only at this stage):

- :class:`LLMRequest`, :class:`LLMResponse` — vendor-neutral request/response
- :class:`Message`, :class:`ContentBlock` family — multimodal content blocks
- :class:`ToolDef`, :class:`ToolChoice`, :class:`ToolCall` — function calling
- :class:`ResponseFormat`, :class:`CacheHint`, :class:`ThinkingConfig`
- :class:`Usage`, :class:`StreamChunk`, :class:`Embeddings`, :class:`ModelInfo`,
  :class:`HealthStatus`, :class:`Capability`

Sub-packages (routing / cache / guardrails / traces / providers credentials)
land as they ship. The :func:`gateway.complete` / :func:`gateway.stream` /
:func:`gateway.embed` facade is added in Task K1.
"""
from __future__ import annotations

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
    "Capability",
    "CacheHint",
    "ContentBlock",
    "Embeddings",
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
]
