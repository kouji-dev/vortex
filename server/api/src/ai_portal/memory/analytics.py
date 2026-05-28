"""Memory analytics rollups.

Four series:
- count over time per (type, scope_kind)
- top recalled memories (last N days)
- recall hit-rate (uses linked to responses)
- extraction outcomes (created / dedupe / refused) by memory_jobs.status
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import Memory, MemoryJob, MemoryUse

logger = logging.getLogger(__name__)


async def count_by_type_scope(
    session: AsyncSession, org_id: _uuid.UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Memory.type, Memory.scope_kind, func.count(Memory.id))
            .where(Memory.org_id == org_id, Memory.deleted_at.is_(None))
            .group_by(Memory.type, Memory.scope_kind)
        )
    ).all()
    return [
        {"type": t.value, "scope_kind": s.value, "count": int(c)}
        for t, s, c in rows
    ]


async def top_recalled(
    session: AsyncSession,
    org_id: _uuid.UUID,
    *,
    days: int = 30,
    limit: int = 20,
) -> list[dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        await session.execute(
            select(
                Memory.id,
                Memory.text,
                func.count(MemoryUse.id).label("uses"),
            )
            .join(MemoryUse, MemoryUse.memory_id == Memory.id)
            .where(Memory.org_id == org_id, MemoryUse.ts >= cutoff)
            .group_by(Memory.id, Memory.text)
            .order_by(desc("uses"))
            .limit(limit)
        )
    ).all()
    return [{"memory_id": str(i), "text": t, "uses": int(c)} for i, t, c in rows]


async def recall_hit_rate(
    session: AsyncSession,
    org_id: _uuid.UUID,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """Fraction of recalls that have a linked response message."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    total = int(
        (
            await session.execute(
                select(func.count(MemoryUse.id))
                .join(Memory, Memory.id == MemoryUse.memory_id)
                .where(Memory.org_id == org_id, MemoryUse.ts >= cutoff)
            )
        ).scalar()
        or 0
    )
    linked = int(
        (
            await session.execute(
                select(func.count(MemoryUse.id))
                .join(Memory, Memory.id == MemoryUse.memory_id)
                .where(
                    Memory.org_id == org_id,
                    MemoryUse.ts >= cutoff,
                    MemoryUse.response_message_id != "",
                )
            )
        ).scalar()
        or 0
    )
    return {"total": total, "linked": linked, "rate": (linked / total) if total else 0.0}


async def extraction_outcomes(
    session: AsyncSession,
    org_id: _uuid.UUID,
    *,
    days: int = 30,
) -> dict[str, int]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        await session.execute(
            select(MemoryJob.status, func.count(MemoryJob.id))
            .where(
                MemoryJob.org_id == org_id,
                MemoryJob.kind == "extract",
                MemoryJob.ended_at.is_not(None),
                MemoryJob.ended_at >= cutoff,
            )
            .group_by(MemoryJob.status)
        )
    ).all()
    return {str(s): int(c) for s, c in rows}


async def rollup_all(
    session: AsyncSession, org_id: _uuid.UUID
) -> dict[str, Any]:
    return {
        "count_by_type_scope": await count_by_type_scope(session, org_id),
        "top_recalled": await top_recalled(session, org_id),
        "recall_hit_rate": await recall_hit_rate(session, org_id),
        "extraction_outcomes": await extraction_outcomes(session, org_id),
    }
