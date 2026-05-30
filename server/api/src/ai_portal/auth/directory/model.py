"""SQLAlchemy ORM model for ``ldap_connections``.

One row per LDAP/AD connection. ``org_id`` is nullable: a NULL row is a
per-deployment connection (self-hosted, single tenant); a non-NULL row is a
per-org connection (multi-tenant). ``kind`` selects the provider factory
(``ldap`` / ``active_directory``). ``bind_secret_enc`` holds the service-account
password wrapped with envelope encryption.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class LdapConnection(Base):
    """Per-org or per-deployment LDAP/AD bind configuration."""

    __tablename__ = "ldap_connections"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ldap", server_default="ldap"
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=389)
    bind_dn: Mapped[str] = mapped_column(String(512), nullable=False)
    bind_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)
    base_dn: Mapped[str] = mapped_column(String(512), nullable=False)
    user_filter: Mapped[str] = mapped_column(
        String(512), nullable=False, default="(uid={username})"
    )
    group_filter: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tls_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    attr_map_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    group_role_map_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
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
