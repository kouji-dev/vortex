"""SQLAlchemy ORM models for guardrails.

Two tables, both org-scoped:

- ``guardrail_policies(id, org_id, name, bundle_json)`` — named bundle of
  guardrails + per-step action. The bundle is opaque JSON shaped like::

      {
        "input": [
          {"name": "secret_scanner", "on_match": "block"},
          {"name": "presidio", "config": {"entities": ["EMAIL_ADDRESS"]},
           "on_match": "redact"}
        ],
        "output": [{"name": "presidio", "on_match": "redact"}]
      }

- ``guardrail_violations(id, org_id, request_id, guardrail, verdict,
  evidence_json, ts)`` — one row per non-``allow`` verdict produced by the
  pipeline. ``evidence_json`` carries the :class:`Match` list and reason.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class GuardrailPolicy(Base):
    """A named bundle of guardrails + actions, scoped to an org."""

    __tablename__ = "guardrail_policies"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_guardrail_policies_org_name"),
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
    bundle_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GuardrailViolation(Base):
    """One non-allow verdict recorded by the pipeline."""

    __tablename__ = "guardrail_violations"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('redact', 'block', 'flag')",
            name="ck_guardrail_violations_verdict",
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
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    guardrail: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ["GuardrailPolicy", "GuardrailViolation"]
