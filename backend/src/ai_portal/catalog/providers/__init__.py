"""LLM provider registry + factory.

Use ``LlmProviderFactory.create(settings, model)`` — or the thin
``get_chat_provider`` wrapper — to get the right provider for a model.

Routing:
- Anthropic model + ``use_native_anthropic`` → ``AnthropicNativeChatProvider``
- Gemini model + ``use_native_gemini`` → ``GeminiNativeChatProvider``
- Otherwise (OpenAI-compatible, or native flags off) → ``LangChainChatProvider``
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_portal.catalog.providers.base import BaseLlmProvider
from ai_portal.catalog.providers.langchain import LangChainChatProvider
from ai_portal.catalog.providers.protocol import ChatProvider

if TYPE_CHECKING:
    from ai_portal.core.config import Settings


class LlmProviderFactory:
    """Factory for chat providers.

    Stateless — safe to instantiate per request or call as a classmethod.
    """

    @classmethod
    def create(cls, settings: "Settings", model: str | None = None) -> ChatProvider:
        """Pick the best provider for *model*."""
        from ai_portal.catalog.providers.routing import (
            _is_anthropic_style_model,
            _is_gemini_model,
        )

        m = (model or settings.chat_default_api_model or "").strip()

        if _is_anthropic_style_model(m) and getattr(settings, "use_native_anthropic", True):
            from ai_portal.catalog.providers.anthropic_native import (
                AnthropicNativeChatProvider,
            )
            return AnthropicNativeChatProvider(settings)

        if _is_gemini_model(m) and getattr(settings, "use_native_gemini", True):
            from ai_portal.catalog.providers.gemini_native import (
                GeminiNativeChatProvider,
            )
            return GeminiNativeChatProvider(settings)

        return LangChainChatProvider(settings)


def get_chat_provider(settings: "Settings", model: str | None = None) -> ChatProvider:
    """Thin wrapper over ``LlmProviderFactory.create`` — keeps existing imports working."""
    return LlmProviderFactory.create(settings, model)


__all__ = [
    "BaseLlmProvider",
    "ChatProvider",
    "LangChainChatProvider",
    "LlmProviderFactory",
    "get_chat_provider",
]
