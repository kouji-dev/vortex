"""SQLAlchemy ORM model for rbac_policy."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class RbacPolicy(Base):
    __tablename__ = "rbac_policy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, unique=True)
    model_allowlist: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    model_role_bindings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    capability_role_bindings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    tool_role_bindings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    default_policy: Mapped[str] = mapped_column(String(8), nullable=False, default="allow")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
