"""Memory background job enqueue helpers.

Lightweight wrapper around ``MemoryJob`` rows. Triggers (chat-on-turn,
conversation-close, scheduled) write rows here; the worker fan-out picks
queued rows and invokes the right extractor / compactor / sweeper.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import MemoryJob, ScopeKind

logger = logging.getLogger(__name__)


async def enqueue(
    session: AsyncSession,
    *,
    org_id: _uuid.UUID,
    kind: str,
    scope_kind: str,
    payload: dict[str, Any],
) -> MemoryJob:
    """Insert a queued memory job."""
    job = MemoryJob(
        org_id=org_id,
        kind=kind,
        scope_kind=ScopeKind(scope_kind),
        payload_json=payload,
        status="queued",
    )
    session.add(job)
    await session.flush()
    return job


async def claim_next(
    session: AsyncSession, *, kind: str | None = None
) -> MemoryJob | None:
    """Pop the oldest queued job (best-effort; not contention-safe)."""
    clauses = [MemoryJob.status == "queued"]
    if kind:
        clauses.append(MemoryJob.kind == kind)
    res = await session.execute(
        select(MemoryJob)
        .where(*clauses)
        .order_by(MemoryJob.id)
        .limit(1)
    )
    row = res.scalar_one_or_none()
    if row is None:
        return None
    await session.execute(
        update(MemoryJob)
        .where(MemoryJob.id == row.id, MemoryJob.status == "queued")
        .values(status="running", started_at=datetime.utcnow())
    )
    await session.flush()
    return row


async def finish(
    session: AsyncSession,
    job_id: _uuid.UUID,
    *,
    status: str = "done",
    error: str | None = None,
) -> None:
    await session.execute(
        update(MemoryJob)
        .where(MemoryJob.id == job_id)
        .values(status=status, ended_at=datetime.utcnow(), error=error)
    )
    await session.flush()


async def watermark(session: AsyncSession, conversation_id: int | str) -> int | None:
    """Highest source turn id already extracted for a conversation."""
    res = await session.execute(
        select(MemoryJob)
        .where(
            MemoryJob.kind == "extract",
            MemoryJob.payload_json["conversation_id"].astext == str(conversation_id),
            MemoryJob.status == "done",
        )
        .order_by(MemoryJob.ended_at.desc())
        .limit(1)
    )
    row = res.scalar_one_or_none()
    if row is None:
        return None
    try:
        return int(row.payload_json.get("last_turn_id") or 0)
    except Exception:
        return None
