from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ai_portal.config import Settings, get_settings
from ai_portal.services.llm_providers import get_chat_provider


def chat_completions(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    return get_chat_provider(settings).complete(messages, model=None)


def chat_completions_stream_deltas(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    settings: Settings | None = None,
) -> Iterator[str]:
    settings = settings or get_settings()
    yield from get_chat_provider(settings).stream_deltas(messages, model=model)


def chat_completions_stream_with_tools(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> Iterator[dict[str, Any]]:
    settings = settings or get_settings()
    yield from get_chat_provider(settings).stream_deltas_with_tools(
        messages, model=model, tools=tools
    )
