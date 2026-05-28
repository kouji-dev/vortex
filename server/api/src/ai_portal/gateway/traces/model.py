"""SQLAlchemy ORM for request_traces (gateway).

Monthly partitioned by ``ts``. One row per LLM gateway request.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

# Import orgs ORM so the FK target table is registered in Base.metadata.
import ai_portal.auth.model  # noqa: F401,E402
from ai_portal.core.db.base import Base


class RequestTrace(Base):
    __tablename__ = "request_traces"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    route: Mapped[str] = mapped_column(String(64), nullable=False)
    model_requested: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_cache_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_cache_write: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_cents: Mapped[float] = mapped_column(
        Numeric(14, 6), nullable=False, default=0
    )
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        primary_key=True,
    )
