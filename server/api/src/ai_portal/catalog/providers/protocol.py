"""Provider interface for chat completions (multi-vendor: Anthropic, OpenAI, …)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol

from ai_portal.catalog.providers.events import ProviderStreamEvent


class ChatProvider(Protocol):
    """One vendor/backend behind a stable portal API shape."""

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
