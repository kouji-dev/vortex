"""Chat completions via LiteLLM (vendor-neutral: base URL + model id)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import litellm

from ai_portal.config import Settings
from ai_portal.services.llm_connect import normalize_openai_compatible_base
from ai_portal.services.model_access import effective_chat_model

logger = logging.getLogger(__name__)

# Retired Anthropic snapshot ids still stored on conversations / old catalog rows.
_ANTHROPIC_DEPRECATED_MODEL_IDS: dict[str, str] = {
    "claude-3-5-haiku-20241022": "claude-haiku-4-5",
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-5-20250929",
    "claude-3-opus-20240229": "claude-opus-4-6",
    "claude-3-7-sonnet-20250219": "claude-sonnet-4-6",
    # Dated snapshot rejected by the Anthropic API; canonical id is the alias.
    "claude-opus-4-6-20260205": "claude-opus-4-6",
    "claude-opus-4-5": "claude-opus-4-5-20251101",
}


def remap_deprecated_litellm_model(model: str) -> str:
    """Rewrite retired Anthropic model strings to current API ids (no DB migration required)."""
    raw = (model or "").strip()
    if not raw:
        return raw
    key = raw.lower()
    if key.startswith("anthropic/"):
        key = key.removeprefix("anthropic/")
    replacement = _ANTHROPIC_DEPRECATED_MODEL_IDS.get(key)
    if replacement is None:
        return raw
    logger.debug("litellm_model_remap_deprecated", extra={"from": raw, "to": replacement})
    return replacement


def normalize_litellm_model_id_for_completion(model: str) -> str:
    """Map catalog-style ids to LiteLLM provider-prefixed ids (required by recent LiteLLM)."""
    raw = (model or "").strip()
    if not raw:
        return raw
    lower = raw.lower()
    if lower.startswith("anthropic/"):
        return raw
    if lower.startswith("claude-") or lower.startswith("claude/"):
        return f"anthropic/{raw}"
    return raw


def _is_anthropic_litellm_model(model: str) -> bool:
    m = (model or "").strip().lower()
    return (
        m.startswith("anthropic/")
        or m.startswith("claude-")
        or m.startswith("claude/")
    )


def litellm_completion_kwargs(settings: Settings, model: str) -> dict[str, Any]:
    """LiteLLM auth + base URL. Claude uses Anthropic key; OpenAI/Azure use LLM_API_KEY + base."""
    if _is_anthropic_litellm_model(model):
        key = settings.anthropic_api_key.strip() or settings.llm_api_key.strip()
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY or LLM_API_KEY must be set for Claude models "
                "(add one to your .env; see .env.example).",
            )
        return {"api_key": key}
    if not settings.llm_api_key.strip():
        raise ValueError(
            "LLM_API_KEY (or OPENAI_API_KEY) is not set — required for this model "
            "and for embeddings (add to your .env; see .env.example).",
        )
    return {
        "api_key": settings.llm_api_key,
        "api_base": normalize_openai_compatible_base(settings.llm_api_base),
    }


class LiteLlmChatProvider:
    """Chat via LiteLLM using provider-specific keys (OpenAI-compatible vs Anthropic)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

        if settings.langfuse_public_key and settings.langfuse_secret_key:
            logger.info(
                "langfuse_configured",
                extra={
                    "langfuse_host": settings.langfuse_host,
                    "hint": "trace hooks can be added here",
                },
            )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        m = normalize_litellm_model_id_for_completion(
            remap_deprecated_litellm_model(effective_chat_model(self._settings, model)),
        )
        kwargs = litellm_completion_kwargs(self._settings, m)
        response = litellm.completion(
            model=m,
            messages=messages,
            **kwargs,
        )
        if isinstance(response, dict):
            return response
        return response.model_dump()

    def stream_deltas(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> Iterator[str]:
        m = normalize_litellm_model_id_for_completion(
            remap_deprecated_litellm_model(effective_chat_model(self._settings, model)),
        )
        kwargs = litellm_completion_kwargs(self._settings, m)
        stream = litellm.completion(
            model=m,
            messages=messages,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            choice0 = chunk.choices[0]
            delta = getattr(choice0, "delta", None)
            if delta is None:
                continue
            piece = getattr(delta, "content", None)
            if piece:
                yield piece
