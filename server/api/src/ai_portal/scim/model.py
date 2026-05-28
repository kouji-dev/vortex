"""SQLAlchemy ORM models for the SCIM domain.

Three tables:

- ``scim_endpoints``: per-org provisioning endpoint. Stores SHA-256 hash of
  the bearer token plus the active preset (``generic`` / ``okta`` / ``entra``).
- ``scim_groups``: shadow record per SCIM Group with optional ``role_name``
  -> system role mapping.
- ``scim_group_members``: link table.
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class ScimEndpoint(Base):
    """Per-org SCIM endpoint. One bearer token authenticates one endpoint."""

    __tablename__ = "scim_endpoints"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_scim_endpoints_token_hash"),
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
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    preset: Mapped[str] = mapped_column(
        String(32), nullable=False, default="generic", server_default="generic"
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ScimGroup(Base):
    """Shadow group record. ``role_name`` maps members to a system role."""

    __tablename__ = "scim_groups"
    __table_args__ = (
        UniqueConstraint(
            "endpoint_id", "display_name", name="uq_scim_groups_endpoint_display"
        ),
    )

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    endpoint_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scim_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ScimGroupMember(Base):
    """Group <-> user link. ``external_user_id`` covers unresolved members."""

    __tablename__ = "scim_group_members"
    __table_args__ = (
        UniqueConstraint(
            "group_id", "user_id", name="uq_scim_group_members_group_user"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scim_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
