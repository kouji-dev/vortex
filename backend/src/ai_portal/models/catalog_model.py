from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.db.base import Base


class CatalogModel(Base):
    """Catalog row; ``requires_entitlement`` gates use until WS-ENT."""

    __tablename__ = "catalog_models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    litellm_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    effort: Mapped[str] = mapped_column(String(16), default="default")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    requires_entitlement: Mapped[bool] = mapped_column(Boolean, default=False)
    request_access_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    catalog_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
