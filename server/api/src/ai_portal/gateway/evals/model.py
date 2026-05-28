"""SQLAlchemy ORM models for the gateway eval framework.

Two tables:

- :class:`ModelEval` — the test set. ``test_set_json`` shape:

  .. code-block:: json

      {
        "records": [
          {"id": "rec-1", "input": "2+2=", "expected": "4", "judge": "exact"},
          ...
        ]
      }

- :class:`ModelEvalRun` — one execution of an eval against one target
  model. ``results_json`` is the per-record outcome; ``summary_json``
  aggregates ``pass_rate`` / ``p95_latency_ms`` / ``total_cost_cents``.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class ModelEval(Base):
    """A named test set scoped to an org."""

    __tablename__ = "model_evals"

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
    test_set_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ModelEvalRun(Base):
    """One run of an eval against one concrete target model."""

    __tablename__ = "model_eval_runs"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    eval_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_evals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_model: Mapped[str] = mapped_column(String(128), nullable=False)
    results_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ["ModelEval", "ModelEvalRun"]
