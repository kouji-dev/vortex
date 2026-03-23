"""Chat via LiteLLM (OpenAI-compatible gateway or direct vendor URL)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_portal.services.llm_providers.litellm_chat import LiteLlmChatProvider
from ai_portal.services.llm_providers.protocol import ChatProvider

if TYPE_CHECKING:
    from ai_portal.config import Settings


def get_chat_provider(settings: Settings) -> ChatProvider:
    return LiteLlmChatProvider(settings)


__all__ = [
    "ChatProvider",
    "LiteLlmChatProvider",
    "get_chat_provider",
]
