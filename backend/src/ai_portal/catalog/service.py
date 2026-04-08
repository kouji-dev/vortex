# src/ai_portal/catalog/service.py
from __future__ import annotations

from sqlalchemy.orm import Session

from ai_portal.catalog.definitions import OPTIONAL_CATALOG_API_MODEL_IDS
from ai_portal.catalog.repository import (
    get_active_catalog_model_by_slug,
    get_active_catalog_models_by_api_model_id,
)
from ai_portal.core.config import Settings, get_settings
from ai_portal.chat.schemas import CapabilityToggles, ConversationSettings

_DEFAULT_CATALOG_SLUG_PRIORITY = (
    "google-gemini-2-5-flash-lite",   # cheapest Gemini tier (preferred default)
    "anthropic-claude-haiku-4-5",     # fallback if Gemini key not configured
    "openai-o3-mini",                 # OpenAI fallback
)


def effective_chat_model(settings: Settings, requested: str | None) -> str:
    m = (requested or settings.chat_default_api_model).strip()
    if not m:
        raise ValueError(
            "No chat model configured (CHAT_DEFAULT_API_MODEL or per-request model)"
        )
    return m


def validate_catalog_model_id(raw: str) -> None:
    s = (raw or "").strip()
    if not s:
        msg = "catalog api_model_id is empty"
        raise ValueError(msg)
    if s in OPTIONAL_CATALOG_API_MODEL_IDS:
        return


def resolve_stored_model_to_chat_model(db: Session, stored: str) -> str:
    s = (stored or "").strip()
    if not s:
        return s
    slug_row = get_active_catalog_model_by_slug(db, s)
    if slug_row is not None:
        return slug_row.api_model_id
    api_rows = get_active_catalog_models_by_api_model_id(db, s)
    if len(api_rows) == 1:
        return api_rows[0].api_model_id
    if len(api_rows) > 1:
        api_rows.sort(key=lambda r: (r.sort_order, r.id))
        return api_rows[0].api_model_id
    return s


def resolve_default_conversation_api_model(db: Session) -> str:
    for slug in _DEFAULT_CATALOG_SLUG_PRIORITY:
        row = get_active_catalog_model_by_slug(db, slug)
        if row is not None:
            return row.api_model_id
    return get_settings().chat_default_api_model


def resolve_default_conversation_stored_model(db: Session) -> str:
    for slug in _DEFAULT_CATALOG_SLUG_PRIORITY:
        row = get_active_catalog_model_by_slug(db, slug)
        if row is not None:
            return row.slug
    return get_settings().chat_default_api_model


def default_conversation_settings() -> ConversationSettings:
    return ConversationSettings(capabilities=CapabilityToggles())
