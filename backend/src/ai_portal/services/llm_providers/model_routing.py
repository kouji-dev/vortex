"""Chat model id normalization and credentials (Anthropic vs OpenAI-compatible).

Catalog stores vendor API model strings in ``catalog_models.api_model_id``; runtime
chat uses LangChain vendor clients.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_portal.config import Settings
from ai_portal.services.llm_connect import normalize_openai_compatible_base

logger = logging.getLogger(__name__)

# Retired Anthropic snapshot ids still stored on conversations / old catalog rows.
_ANTHROPIC_DEPRECATED_MODEL_IDS: dict[str, str] = {
    "claude-3-5-haiku-20241022": "claude-haiku-4-5",
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-5-20250929",
    "claude-3-opus-20240229": "claude-opus-4-6",
    "claude-3-7-sonnet-20250219": "claude-sonnet-4-6",
    "claude-opus-4-6-20260205": "claude-opus-4-6",
    "claude-opus-4-5": "claude-opus-4-5-20251101",
}


def remap_deprecated_chat_model(model: str) -> str:
    """Map retired Anthropic ids to current API ids (no DB migration)."""
    raw = (model or "").strip()
    if not raw:
        return raw
    key = raw.lower()
    if key.startswith("anthropic/"):
        key = key.removeprefix("anthropic/")
    replacement = _ANTHROPIC_DEPRECATED_MODEL_IDS.get(key)
    if replacement is None:
        return raw
    logger.debug("chat_model_remap_deprecated", extra={"from": raw, "to": replacement})
    return replacement


def normalize_chat_model_id_for_tests(model: str) -> str:
    """Map catalog ids to provider-prefixed strings (unit tests)."""
    raw = (model or "").strip()
    if not raw:
        return raw
    lower = raw.lower()
    if lower.startswith("anthropic/"):
        return raw
    if lower.startswith("claude-") or lower.startswith("claude/"):
        return f"anthropic/{raw}"
    return raw


def _is_anthropic_style_model(model: str) -> bool:
    """True for vendor API ids and catalog slugs (e.g. ``anthropic-claude-haiku-4-5``)."""
    m = (model or "").strip().lower()
    return (
        m.startswith("anthropic/")
        or m.startswith("anthropic-claude-")
        or m.startswith("claude-")
        or m.startswith("claude/")
    )


def chat_provider_credential_kwargs(settings: Settings, model: str) -> dict[str, Any]:
    """Credentials for chat: OpenAI-compatible (key+base) or Anthropic (key)."""
    if _is_anthropic_style_model(model):
        key = settings.anthropic_api_key.strip()
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set — required for Claude / Anthropic chat models "
                "(add to your repo root .env). OpenAI chat and OpenAI embeddings use "
                "OPENAI_API_KEY; Voyage embeddings use VOYAGE_API_KEY.",
            )
        return {"api_key": key}
    if not settings.openai_api_key.strip():
        raise ValueError(
            "OPENAI_API_KEY is not set — required for OpenAI-compatible chat models "
            "(add to your repo root .env). Anthropic chat uses ANTHROPIC_API_KEY.",
        )
    return {
        "api_key": settings.openai_api_key,
        "api_base": normalize_openai_compatible_base(settings.openai_api_base),
    }


def normalize_model_id_for_langchain_chat(model: str) -> str:
    """Normalize catalog/stored id for ChatAnthropic or ChatOpenAI."""
    m = remap_deprecated_chat_model((model or "").strip())
    if not m:
        return m
    lower = m.lower()
    if lower.startswith("anthropic/"):
        return m.split("/", 1)[1]
    # Catalog slug: "anthropic-claude-*" → LangChain expects "claude-*"
    if lower.startswith("anthropic-claude-"):
        return m[lower.index("claude-") :]
    if lower.startswith("claude/"):
        return m.removeprefix("claude/")
    return m


def is_langchain_anthropic_model(model_id: str) -> bool:
    mid = normalize_model_id_for_langchain_chat(model_id)
    lowered = mid.lower()
    return lowered.startswith("claude-") or lowered.startswith("claude/")
