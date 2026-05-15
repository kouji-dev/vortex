"""Generate a short conversation title from the user's first message.

Single synchronous LLM call; the orchestrator runs it in a background task
(via ``asyncio.to_thread``) after kicking off the user-visible message stream
so the title arrives shortly without blocking the streamed reply.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Conversations with this title (or empty / None) are treated as un-titled and
# eligible for auto-title generation. Kept in sync with the frontend default.
DEFAULT_PLACEHOLDER_TITLES = {"", "New conversation", "Untitled"}

_MAX_TITLE_CHARS = 60
_SYSTEM_PROMPT = (
    "Title generator.\n"
    "- Reply with ONLY a 3-6 word title. No quotes. No trailing punctuation.\n"
    "- Capture the topic of the user message. Use the user's language."
)


def needs_title(current: str | None) -> bool:
    return (current or "").strip() in DEFAULT_PLACEHOLDER_TITLES


def _clean(raw: str) -> str:
    # Drop wrapping quotes, trailing punctuation, collapse whitespace, cap length.
    s = raw.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip("\"'`“”‘’ ")
    s = re.sub(r"[.!?;,:]+$", "", s)
    if len(s) > _MAX_TITLE_CHARS:
        s = s[: _MAX_TITLE_CHARS - 1].rstrip() + "…"
    return s


def generate_title(provider: Any, model: str, user_text: str) -> str:
    """Returns the cleaned title, or empty string on failure / empty output."""
    excerpt = (user_text or "").strip()[:1000]
    if not excerpt:
        return ""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"First user message:\n\n{excerpt}"},
    ]
    try:
        resp = provider.complete(messages, model=model)
        text = resp["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("title_generation_provider_failed", extra={"err": str(exc)})
        return ""
    return _clean(text or "")
