"""SQLAlchemy ORM model for ``rate_limit_rules``.

One row = one limit. The triple (``scope_json``, ``dimension``, ``period_seconds``)
identifies the bucket; ``limit_value`` + ``burst`` parameterise it.

``scope_json`` shape (any combination, missing keys = match-all):

.. code-block:: json

    {"actor_user_id": 42}
    {"api_key_id": 7}
    {"model": "claude-sonnet-4-6"}
    {"team_id": "...", "model": "..."}
    {}                                  # org-wide default

``dimension`` is one of:

- ``rpm``                  — requests per period
- ``tpm``                  — tokens per period
- ``concurrent_requests``  — in-flight requests (period_seconds ignored)
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class RateLimitRule(Base):
    """A single rate-limit rule scoped to an org."""

    __tablename__ = "rate_limit_rules"
    __table_args__ = (
        CheckConstraint(
            "dimension IN ('rpm', 'tpm', 'concurrent_requests')",
            name="ck_rate_limit_rules_dimension",
        ),
        CheckConstraint(
            "period_seconds > 0", name="ck_rate_limit_rules_period_positive"
        ),
        CheckConstraint("limit_value >= 0", name="ck_rate_limit_rules_limit_nonneg"),
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
    scope_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    period_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False)
    burst: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
