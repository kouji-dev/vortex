"""Provider protocol(s) for chat completions + embeddings + introspection.

Two surfaces live here:

1. :class:`ChatProvider` — **legacy** vendor-shaped protocol. Existing chat
   module (`chat/streaming/orchestrator.py`, memory workers, …) consumes
   this. Methods return vendor-shaped dicts and ``Iterator``\\s. Kept intact
   to avoid a Big Bang refactor of every caller.

2. :class:`LLMProvider` — **canonical** gateway protocol. New, vendor-neutral.
   Methods accept :class:`ai_portal.gateway.LLMRequest` and return
   :class:`LLMResponse` / :class:`StreamChunk`. All bundled providers
   (Anthropic native, Gemini native, LangChain) implement both.

Bundled providers should also expose:

- ``name: str`` — short identifier (``"anthropic"``, ``"gemini"``, …)
- ``capabilities: set[Capability]`` — declared feature set
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol, runtime_checkable

from ai_portal.catalog.providers.events import ProviderStreamEvent
from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    HealthStatus,
    LLMRequest,
    LLMResponse,
    ModelInfo,
    StreamChunk,
)


@runtime_checkable
class ChatProvider(Protocol):
    """One vendor/backend behind a stable portal API shape.

    Legacy protocol — kept for backward compatibility with the chat module.
    New code should target :class:`LLMProvider` instead.
    """

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat result (dict with choices/message shape)."""
        ...

    def complete_structured[T](
        self,
        messages: list[dict[str, str]],
        *,
        schema: type[T],
        model: str | None = None,
    ) -> T:
        """Return a response parsed into *schema* (a Pydantic BaseModel subclass)."""
        ...

    def stream_deltas(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> Iterator[str]:
        """Yield assistant text fragments (streaming)."""
        ...

    def stream_deltas_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield structured event dicts. All providers must emit these types:

        - ``{"type": "delta", "text": str}`` — assistant text fragment.
        - ``{"type": "tool_call", "tool_call": {"name": str, "arguments": str, "id": str}}``
          — client-side tool call; caller dispatches.
        - ``{"type": "server_tool_use", "name": str, "input": dict, "id": str}``
          — provider-executed tool (Anthropic web_search, Gemini grounding).

        New in enterprise build (emitted once per stream, at the end):
        - ``{"type": "usage", "input_tokens": int, "output_tokens": int,
             "cached_input_tokens": int, "cache_creation_input_tokens": int,
             "reasoning_tokens": int | None}``
        - ``{"type": "thinking", "text": str}`` — extended thinking fragments
          (Anthropic only). Stored in ``ChatMessage.extra.thinking``.
        - ``{"type": "citation", "url": str, "title": str | None,
             "snippet": str | None}`` — web-search grounding citation.

        Unknown types must be ignored by consumers (forward compatibility).
        """
        ...

    async def stream(
        self,
        *,
        messages: list[dict],
        model: str,
        settings: dict,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        """Async typed stream yielding ``ProviderStreamEvent`` discriminated-union values."""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    """Canonical gateway protocol — vendor-neutral.

    Adapters wrap one vendor SDK and translate the canonical
    :class:`LLMRequest` to its native format on the way in, and the native
    response back to :class:`LLMResponse` on the way out.

    Every bundled provider declares its :attr:`name` + :attr:`capabilities`
    so the router can pick a candidate that satisfies a request's
    requirements (vision, tools, thinking, cache, …).
    """

    name: str
    capabilities: set[Capability]

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        """Non-streaming completion (canonical types).

        Named ``complete_canonical`` (not just ``complete``) because the
        legacy :class:`ChatProvider` already owns ``complete()`` with a
        vendor-shaped signature. The gateway service calls this method;
        existing chat code keeps calling the legacy ``complete``.
        """
        ...

    async def stream_canonical(self, req: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Streaming completion (canonical chunks)."""
        ...

    async def embed(self, texts: list[str], model: str) -> Embeddings:
        """Embed one or more texts. Raises if the provider has no embedder."""
        ...

    def count_tokens(self, text: str, model: str) -> int:
        """Approximate token count for *text* on *model*."""
        ...

    async def list_models(self) -> list[ModelInfo]:
        """Discover models exposed by this provider."""
        ...

    async def health(self) -> HealthStatus:
        """Lightweight probe — does the provider answer?"""
        ...


__all__ = [
    "ChatProvider",
    "LLMProvider",
]
