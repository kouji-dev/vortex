"""SQLAlchemy ORM model for the ``prompt_cache_entries`` table.

One row per cache key per org. RLS-enforced (org_id matches
``app.current_org_id()`` or ``app.is_rls_bypassed()``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class _Base(DeclarativeBase):
    pass


class PromptCacheEntry(_Base):
    """One cached LLM response keyed by request hash."""

    __tablename__ = "prompt_cache_entries"

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
