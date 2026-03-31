"""Provider interface for chat completions (multi-vendor: Anthropic, OpenAI, …)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol


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
        """Yield dicts: {"type": "delta", "text": str} or {"type": "tool_call", "tool_call": {...}}"""
        ...
