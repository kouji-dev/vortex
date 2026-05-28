"""Importance decay nightly worker.

For each non-pinned, non-deleted memory:
- compute days since last_used_at (or created_at)
- count uses in last 30d
- new_importance = decay_importance(...)
- if importance < 0.05 and no use in 30d → soft-delete
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.decay import decay_importance
from ai_portal.memory.model import Memory, MemoryUse

logger = logging.getLogger(__name__)


async def run_decay(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Apply importance decay + soft-delete cold memories."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=30)
    use_counts_q = (
        select(MemoryUse.memory_id, func.count(MemoryUse.id).label("c"))
        .where(MemoryUse.ts >= cutoff)
        .group_by(MemoryUse.memory_id)
    )
    use_counts = {
        row.memory_id: int(row.c) for row in (await session.execute(use_counts_q)).all()
    }
    rows = (
        await session.execute(
            select(Memory).where(
                and_(Memory.deleted_at.is_(None), Memory.pinned.is_(False))
            )
        )
    ).scalars().all()
    decayed = 0
    cold_deleted = 0
    for m in rows:
        ts = m.last_used_at or m.created_at
        if ts is None:
            continue
        days = max(0.0, (now - ts).total_seconds() / 86400.0)
        new_imp = decay_importance(
            float(m.importance or 0.0),
            days_since_use=days,
            recent_use_count=use_counts.get(m.id, 0),
        )
        if abs(new_imp - float(m.importance or 0.0)) > 1e-4:
            await session.execute(
                update(Memory).where(Memory.id == m.id).values(importance=new_imp)
            )
            decayed += 1
        if new_imp < 0.05 and use_counts.get(m.id, 0) == 0 and days > 30:
            await session.execute(
                update(Memory).where(Memory.id == m.id).values(deleted_at=now)
            )
            cold_deleted += 1
    await session.flush()
    return {"decayed": decayed, "cold_deleted": cold_deleted}
