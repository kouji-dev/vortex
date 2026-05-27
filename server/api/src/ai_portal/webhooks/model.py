"""SQLAlchemy ORM models for the webhooks domain.

Tables:
- ``webhooks``: registered outbound endpoint per org with event-type filter.
- ``webhook_deliveries``: one row per send attempt for a given event.
- ``webhook_event_types``: declared event type catalog (registered at import).
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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


class Webhook(Base):
    """Registered outbound webhook endpoint."""

    __tablename__ = "webhooks"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Hash of the shared secret used for HMAC signing. The plaintext secret is
    # returned to the caller exactly once at creation time.
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    # Encrypted/wrapped secret — kept so the worker can sign outbound payloads.
    # MVP: stored encrypted-at-rest by the DB layer (RLS + at-rest disk crypt).
    # Future: wrap with KMS / app-level cipher.
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    event_types_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WebhookDelivery(Base):
    """One row per delivery attempt for an event.

    ``status`` lifecycle: ``pending`` → ``in_flight`` → (``delivered`` | ``failed``).
    A failed attempt schedules a retry at ``next_attempt_at`` until cap (24h).
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    webhook_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WebhookEventType(Base):
    """Catalog of event types modules may emit.

    Populated at import-time via :func:`register_event_type`. Migration seeds
    the initial control-plane event types; later modules upsert their own
    rows on app startup.
    """

    __tablename__ = "webhook_event_types"
    __table_args__ = (UniqueConstraint("key", name="uq_webhook_event_types_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
