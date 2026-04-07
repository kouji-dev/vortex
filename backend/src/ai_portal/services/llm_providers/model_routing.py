# Re-export shim — real implementation moved to catalog/providers/routing.py
from ai_portal.catalog.providers.routing import (  # noqa: F401
    remap_deprecated_chat_model,
    normalize_chat_model_id_for_tests,
    normalize_model_id_for_langchain_chat,
    is_langchain_anthropic_model,
    chat_provider_credential_kwargs,
    _is_anthropic_style_model,
    _ANTHROPIC_DEPRECATED_MODEL_IDS,
)
