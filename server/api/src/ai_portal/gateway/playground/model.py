"""SQLAlchemy ORM model for ``playground_sessions``.

One row = one saved playground snapshot. ``snapshot_json`` carries the
opaque payload (prompt + system + model + settings + tool defs). Schema
of ``snapshot_json`` is owned by the playground UI; the backend treats it
as a blob and only echoes it on load + executes it on run.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class PlaygroundSession(Base):
    """Saved playground snapshot scoped to an org + user."""

    __tablename__ = "playground_sessions"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["PlaygroundSession"]
