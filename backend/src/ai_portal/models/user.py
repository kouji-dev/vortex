from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.db.base import Base


class User(Base):
    __tablename__ = "users"

    # Existing int PK — kept to avoid breaking FKs in assistants, conversations, etc.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # UUID used as JWT subject for local auth
    uuid: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=_uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    entra_object_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Org membership (nullable until migration backfills existing rows)
    org_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="member", server_default="member"
    )

    # Auth flags
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
