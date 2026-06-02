from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class CatalogModel(Base):
    """Catalog row; ``requires_entitlement`` gates use until WS-ENT."""

    __tablename__ = "catalog_models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    api_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    effort: Mapped[str] = mapped_column(String(16), default="default")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    requires_entitlement: Mapped[bool] = mapped_column(Boolean, default=False)
    usable_in_worker: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False, index=True
    )
    request_access_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    catalog_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GatewayModel(Base):
    """Gateway model catalog — global registry of every concrete provider model.

    Distinct from :class:`CatalogModel` (legacy, org-scoped, chat-UI bound).
    Populated by ``catalog.sync.sync_models`` from each provider's
    ``list_models()`` once per day.

    Shape matches Gateway design spec §Data Model:
    ``models(id, provider, model_id, display_name, capabilities_json,
    price_input_per_1k_cents, price_output_per_1k_cents,
    price_cache_read_per_1k_cents, deprecated_at)``.
    """

    __tablename__ = "gateway_models"
    __table_args__ = (
        UniqueConstraint(
            "provider", "model_id", name="uq_gateway_models_provider_model"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    price_input_per_1k_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    price_output_per_1k_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    price_cache_read_per_1k_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def capabilities(self) -> list[str]:
        """Read alias for ``capabilities_json`` (avoids ambiguous column access)."""
        return list(self.capabilities_json or [])
