"""SQLAlchemy ORM model for ``idp_connections``.

One row per IdP per org. ``kind`` selects the provider factory from the
registry (e.g. ``oidc``, ``saml``). ``config_encrypted`` carries the
provider-specific configuration (client_id, metadata URL, signing certs)
serialized as JSON. The plaintext key/cert material is wrapped at the app
layer in later phases — for now the column holds the serialized JSON blob.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

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


class IdpConnection(Base):
    """Per-org IdP configuration.

    ``sso_required`` enforces SSO-only login for users belonging to this org
    (Phase G6). ``domain`` is the email domain used for auto-routing on
    ``/v1/auth/sso/start`` (Phase G5). Each org may have multiple connections
    (e.g. SAML + OIDC) but only one per (org, kind, domain) tuple.
    """

    __tablename__ = "idp_connections"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "kind",
            "domain",
            name="uq_idp_connections_org_kind_domain",
        ),
    )

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Provider key in the registry — e.g. ``oidc``, ``saml``, ``entra``.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Optional email domain bound to this connection ("acme.com"). Empty
    # string means the connection is not auto-routed by domain.
    domain: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    # JSON blob of provider-specific config (client_id, metadata, certs, ...).
    # Stored as Text so callers can wrap it with app-level encryption later.
    config_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    sso_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
