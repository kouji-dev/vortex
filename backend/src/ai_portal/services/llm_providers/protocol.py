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
        """Non-streaming chat result (OpenAI-shaped dict if needed by callers)."""
        ...

    def stream_deltas(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> Iterator[str]:
        """Yield assistant text fragments (streaming)."""
        ...
