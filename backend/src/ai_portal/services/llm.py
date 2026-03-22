from __future__ import annotations

import logging
from typing import Any

import httpx

from ai_portal.config import Settings, get_settings

logger = logging.getLogger(__name__)


def chat_completions(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")

    url = f"{settings.openai_api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.chat_model,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    if settings.langfuse_public_key and settings.langfuse_secret_key:
        logger.info(
            "langfuse_configured",
            extra={"langfuse_host": settings.langfuse_host, "hint": "trace hooks can be added here"},
        )

    close = client is None
    c = client or httpx.Client(timeout=120.0)
    try:
        r = c.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()
    finally:
        if close:
            c.close()
