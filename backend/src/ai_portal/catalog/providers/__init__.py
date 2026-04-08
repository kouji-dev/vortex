from __future__ import annotations

from typing import TYPE_CHECKING

from ai_portal.catalog.providers.langchain import LangChainChatProvider
from ai_portal.catalog.providers.protocol import ChatProvider

if TYPE_CHECKING:
    from ai_portal.core.config import Settings


def get_chat_provider(settings: "Settings") -> ChatProvider:
    return LangChainChatProvider(settings)


__all__ = [
    "ChatProvider",
    "LangChainChatProvider",
    "get_chat_provider",
]
