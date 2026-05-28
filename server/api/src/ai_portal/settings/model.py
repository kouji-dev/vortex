"""ORM models for org_settings + module_flags.

- ``org_settings(org_id, key, value_json)`` — generic per-org KV.
- ``module_flags(org_id, module, enabled, gates_json)`` — per-module toggle +
  optional named feature gates.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class OrgSetting(Base):
    """Generic per-org KV. ``value_json`` may hold any JSON-serialisable shape."""

    __tablename__ = "org_settings"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "key", name="pk_org_settings"),
    )

    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ModuleFlag(Base):
    """Per-module enable/disable + named gates.

    Modules default to enabled. Absence of a row → enabled. A row with
    ``enabled=false`` blocks the module for that org. ``gates_json`` carries
    fine-grained feature toggles inside the module (default ``False``).
    """

    __tablename__ = "module_flags"
    __table_args__ = (
        PrimaryKeyConstraint("org_id", "module", name="pk_module_flags"),
    )

    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    gates_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
