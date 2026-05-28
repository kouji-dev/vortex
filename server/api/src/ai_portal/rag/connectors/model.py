"""Connector-related ORM models for the RAG module.

These live in ``ai_portal.rag.connectors.model`` rather than alongside the
legacy ``knowledge_base.model`` to keep this subpackage self-contained — the
plan calls for ``rag/connectors/`` to be the new home of all connector
state.

Tables:

- ``kb_connectors``    — one configurable connector instance per KB.
  Configuration is stored as opaque ciphertext (encryption handled at the
  service layer; this row only sees bytes).
- ``kb_sync_runs``     — one row per orchestrated sync. Tracks counts and
  outcome.
- ``kb_sync_errors``   — append-only per-document failure log scoped to a
  sync run.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class KbConnector(Base):
    """A connector instance bound to a KB.

    - ``kind``               — registry key (e.g. ``"web_crawler"``).
    - ``config_encrypted``   — opaque ciphertext; decrypted in the service
      layer via the Control-Plane KEK. Plaintext shape is connector-specific
      JSON (validated against the manifest's ``config_schema``).
    - ``schedule_cron``      — standard 5-field cron expression or ``None``
      for webhook-only / manual connectors.
    - ``last_sync_at``       — UTC timestamp of the most recent run start.
    - ``last_cursor``        — opaque delta cursor persisted across runs.
    - ``enabled``            — soft kill-switch; disables scheduling without
      deleting the row.
    """

    __tablename__ = "kb_connectors"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    kb_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    config_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, default=b""
    )
    schedule_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KbSyncRun(Base):
    """One row per sync invocation.

    - ``status``  — ``"running" | "success" | "failed" | "partial"``.
    - ``docs_*``  — counters incremented as the orchestrator drains the
      connector's ``discover()`` stream.
    """

    __tablename__ = "kb_sync_runs"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    connector_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("kb_connectors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="running"
    )
    docs_added: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    docs_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    docs_deleted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    errors_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cursor_after: Mapped[str | None] = mapped_column(Text, nullable=True)


class KbSyncError(Base):
    """Per-document failure scoped to a sync run.

    A run can complete with status ``"partial"`` if some docs failed but
    others succeeded — those failures are captured here with the source URI
    and error message for ops visibility.
    """

    __tablename__ = "kb_sync_errors"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    run_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("kb_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
