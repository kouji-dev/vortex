"""Resolve default chat model (LiteLLM id) for new conversations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.config import get_settings
from ai_portal.models import CatalogModel
from ai_portal.schemas.conversation_settings import (
    CapabilityToggles,
    ConversationSettings,
)

# Matches seed slugs in ``seed_catalog_models`` (preferred default when present).
_DEFAULT_CATALOG_SLUG_PRIORITY = (
    "anthropic-claude-haiku-4-5",
    "openai-o3-mini",
)


def resolve_default_conversation_litellm_model(db: Session) -> str:
    """LiteLLM id for the preferred default catalog row (for callers that need API id only)."""
    for slug in _DEFAULT_CATALOG_SLUG_PRIORITY:
        row = db.scalars(
            select(CatalogModel)
            .where(CatalogModel.slug == slug)
            .where(CatalogModel.is_active.is_(True))
            .limit(1)
        ).first()
        if row is not None:
            return row.litellm_model_id
    return get_settings().chat_default_litellm_model


def resolve_default_conversation_stored_model(db: Session) -> str:
    """Value persisted on new conversations: catalog **slug** when possible, else settings id."""
    for slug in _DEFAULT_CATALOG_SLUG_PRIORITY:
        row = db.scalars(
            select(CatalogModel)
            .where(CatalogModel.slug == slug)
            .where(CatalogModel.is_active.is_(True))
            .limit(1)
        ).first()
        if row is not None:
            return row.slug
    return get_settings().chat_default_litellm_model


def default_conversation_settings() -> ConversationSettings:
    return ConversationSettings(
        capabilities=CapabilityToggles(),
    )
