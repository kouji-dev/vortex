"""Provider credentials row — encrypted at rest with AES-GCM via KEK."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class ProviderCredential(Base):
    """Per-org provider API key, AES-GCM encrypted ciphertext.

    One row per (org_id, provider, label). ``label`` lets an org keep multiple
    keys for the same provider (e.g. ``prod`` vs ``staging``). Health probe
    writes ``last_health_at`` + ``healthy`` after calling provider ``/models``
    or equivalent.
    """

    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "provider", "label", name="uq_provider_credentials_org_provider_label"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False, server_default="default")
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    healthy: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
