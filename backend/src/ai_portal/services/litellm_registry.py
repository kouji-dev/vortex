"""Align portal catalog ``litellm_model_id`` values with the installed LiteLLM package.

We validate using ``litellm.get_model_info`` on the **same** model string the chat
provider passes to ``litellm.completion`` (deprecated-id remap + Anthropic prefix).
That tracks LiteLLM's provider routing tables, not a hand-maintained duplicate list.
"""

from __future__ import annotations

from litellm import get_model_info

from ai_portal.litellm_catalog_definitions import OPTIONAL_LITELLM_MODEL_IDS
from ai_portal.services.llm_providers.litellm_chat import (
    normalize_litellm_model_id_for_completion,
    remap_deprecated_litellm_model,
)


def completion_model_id_for_catalog_row(stored_litellm_model_id: str) -> str:
    """Model id as used by ``LiteLlmChatProvider`` / ``litellm.completion``."""
    raw = (stored_litellm_model_id or "").strip()
    return normalize_litellm_model_id_for_completion(remap_deprecated_litellm_model(raw))


def validate_catalog_litellm_model_id(stored_litellm_model_id: str) -> None:
    """Raise ``ValueError`` if LiteLLM does not recognize this catalog model id."""
    raw = (stored_litellm_model_id or "").strip()
    if raw in OPTIONAL_LITELLM_MODEL_IDS:
        return
    mid = completion_model_id_for_catalog_row(stored_litellm_model_id)
    if not mid:
        msg = "catalog litellm_model_id is empty"
        raise ValueError(msg)
    try:
        get_model_info(mid)
    except Exception as e:
        msg = (
            f"LiteLLM does not recognize model id {mid!r} "
            f"(from catalog litellm_model_id={stored_litellm_model_id!r}). "
            "Upgrade litellm or adjust the catalog seed — see litellm.model_cost / docs."
        )
        raise ValueError(msg) from e
