"""SQLAlchemy ORM models for routing — policies + aliases.

``RoutingPolicy``:
    id, org_id, name, strategy, rules_json, created_at

``ModelAlias``:
    id, org_id, alias, routing_policy_id

Both are org-scoped with row-level security; the alembic revision installs
the RLS policy.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

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

_STRATEGY_NAMES = (
    "static",
    "priority",
    "weighted",
    "cost_optimized",
    "latency_optimized",
    "capability_match",
    "custom_rules",
)


class RoutingPolicy(Base):
    """Per-org routing policy.

    ``strategy`` is the name of a bundled strategy (see
    :mod:`ai_portal.gateway.routing.registry`). ``rules_json`` carries the
    strategy-specific configuration documented on each strategy class.
    """

    __tablename__ = "routing_policies"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_routing_policies_org_name"),
        CheckConstraint(
            f"strategy IN ({', '.join(repr(n) for n in _STRATEGY_NAMES)})",
            name="ck_routing_policies_strategy",
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
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    rules_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelAlias(Base):
    """Virtual model name that resolves to a :class:`RoutingPolicy`.

    A request whose ``model`` matches ``alias`` (per-org, case-sensitive)
    triggers routing under ``routing_policy_id``. Aliases are unique per
    org so ``"smart"`` can resolve differently for different tenants.
    """

    __tablename__ = "model_aliases"
    __table_args__ = (
        UniqueConstraint("org_id", "alias", name="uq_model_aliases_org_alias"),
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
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    routing_policy_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("routing_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
