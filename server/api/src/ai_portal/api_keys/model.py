"""SQLAlchemy ORM models for the control-plane API keys domain.

Table ``api_keys``:

- ``id``                 — UUID primary key.
- ``org_id``             — owning org (RLS-scoped, cascade-deleted).
- ``actor_user_id``      — NULL for service keys; otherwise the user the key
                           "acts as" (personal key).
- ``name``               — short label.
- ``prefix``             — first 12 chars of plaintext (``ap_xxxxxxxxx``) — used
                           by the UI to identify a key without disclosing it.
- ``hash``               — SHA-256 hex of the plaintext secret.
- ``scopes_json``        — list[str] of permission keys (flat).
- ``expires_at``         — optional hard expiry.
- ``last_used_at``       — bumped on successful verify (best-effort).
- ``revoked_at``         — soft-revoke timestamp; verify must reject.
- ``created_at``         — record creation.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class ApiKey(Base):
    """Control-plane API key — minted per-org, identified by ``ap_`` prefix."""

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("hash", name="uq_api_keys_hash"),
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
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
