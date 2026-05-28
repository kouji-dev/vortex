"""SQLAlchemy ORM models for audit_events + retention/export.

Phase D extends the original ``audit_events`` row with a Merkle hash chain
(``prev_hash`` + ``hash``) and a stable external ``event_id`` UUID. The table
is partitioned by month (PG-native RANGE on ``created_at``); SQLAlchemy
treats the partitioned table as a normal table for ORM purposes.

Append-only is enforced at the DB layer by a trigger (see migrations 029 +
039). Service code never issues UPDATE/DELETE.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), default=_uuid.uuid4, nullable=False)
    org_id: Mapped[_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    actor_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    payload_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    actor_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditRetentionConfig(Base):
    __tablename__ = "audit_retention_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, unique=True)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2555)
    sink_configs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditExportJob(Base):
    __tablename__ = "audit_export_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    requested_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fmt: Mapped[str] = mapped_column(String(16), nullable=False)
    destination: Mapped[str] = mapped_column(String(32), nullable=False, default="download")
    filter_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    blob_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
