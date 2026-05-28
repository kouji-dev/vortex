"""Shared base class for native LLM providers (Anthropic, Gemini).

Consolidates the identical helpers every native provider ends up duplicating:
- stream_deltas() — filters the unified event stream for plain text deltas.
- complete_structured() — not supported by native providers (LangChain only).
- _extract_system_text() — pull the system message out of the message list.
- _resolved_model() — apply ``remap_deprecated_chat_model`` + provider-specific normalization.

Subclasses only need to implement ``complete`` and ``stream_deltas_with_tools``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from typing import Any

from ai_portal.catalog.providers.canonical_adapter import CanonicalProviderMixin
from ai_portal.catalog.providers.routing import remap_deprecated_chat_model
from ai_portal.core.config import Settings


class BaseLlmProvider(CanonicalProviderMixin, ABC):
    """Abstract base for native LLM providers.

    Concrete subclasses wire up a vendor SDK and implement ``complete`` +
    ``stream_deltas_with_tools``. Everything else is shared.
    """

    _normalize_model_id: Callable[[str], str] = staticmethod(lambda m: m)  # overridden

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ── shared helpers ──────────────────────────────────────────────────

    def _resolved_model(self, model: str | None) -> str:
        raw = remap_deprecated_chat_model(
            (model or self._settings.chat_default_api_model or "").strip()
        )
        return type(self)._normalize_model_id(raw)

    @staticmethod
    def _extract_system_text(messages: list[dict[str, Any]]) -> str:
        for m in messages:
            if m.get("role") == "system":
                return str(m.get("content") or "")
        return ""

    # ── shared implementations ──────────────────────────────────────────

    def stream_deltas(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> Iterator[str]:
        """Plain text stream (filters the structured event stream)."""
        for piece in self.stream_deltas_with_tools(messages, model=model):
            if isinstance(piece, dict) and piece.get("type") == "delta":
                yield piece["text"]

    def complete_structured[T](
        self,
        messages: list[dict[str, str]],
        *,
        schema: type[T],
        model: str | None = None,
    ) -> T:
        raise NotImplementedError(
            f"{type(self).__name__} does not support structured output — use LangChain provider"
        )

    # ── abstract methods (subclasses implement) ─────────────────────────

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat completion."""

    @abstractmethod
    def stream_deltas_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Structured event stream. See ``ChatProvider`` protocol for event schema."""
