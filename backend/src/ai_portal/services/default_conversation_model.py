# Re-export shim — real implementation moved to catalog/service.py
from ai_portal.catalog.service import (  # noqa: F401
    resolve_default_conversation_api_model,
    resolve_default_conversation_stored_model,
    default_conversation_settings,
)
