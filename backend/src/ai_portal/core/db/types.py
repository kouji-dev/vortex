"""SQLAlchemy JSON adapters and tenant repository utilities.

ConversationSettingsJSON lives here as the canonical location.
TenantRepository is re-exported from db.tenant (its canonical location) so that
patch("ai_portal.db.tenant.select") in existing tests continues to work.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, TypeDecorator

from ai_portal.schemas.conversation_settings import ConversationSettings

# TenantRepository stays in db.tenant so existing patch-based tests keep working.
from ai_portal.db.tenant import TenantRepository  # noqa: F401


class ConversationSettingsJSON(TypeDecorator):
    """JSON ↔ :class:`ConversationSettings` in Python.

    Uses generic :class:`~sqlalchemy.JSON` so SQLite ``create_all`` works in tests;
    on PostgreSQL the dialect still maps this to JSONB where appropriate.

    ``none_as_null`` maps Python ``None`` to SQL NULL (not JSON ``null``),
    satisfying ``ck_chat_conversations_settings_is_object``.
    """

    impl = JSON(none_as_null=True)
    cache_ok = True

    def process_bind_param(
        self, value: ConversationSettings | dict[str, Any] | None, dialect: Any
    ) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, ConversationSettings):
            return value.model_dump(mode="json", exclude_none=True)
        if isinstance(value, dict):
            return ConversationSettings.model_validate(value).model_dump(
                mode="json", exclude_none=True
            )
        raise TypeError(
            f"settings must be ConversationSettings, dict, or None, got {type(value)}"
        )

    def process_result_value(
        self, value: dict[str, Any] | None, dialect: Any
    ) -> ConversationSettings | None:
        if value is None:
            return None
        return ConversationSettings.model_validate(value)
