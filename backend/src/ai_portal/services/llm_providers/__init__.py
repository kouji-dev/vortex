"""Chat via LangChain (Anthropic or OpenAI-compatible base URL)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_portal.services.llm_providers.langchain_chat import LangChainChatProvider
from ai_portal.services.llm_providers.protocol import ChatProvider

if TYPE_CHECKING:
    from ai_portal.config import Settings


def get_chat_provider(settings: Settings) -> ChatProvider:
    return LangChainChatProvider(settings)


__all__ = [
    "ChatProvider",
    "LangChainChatProvider",
    "get_chat_provider",
]
