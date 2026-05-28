"""TTL sweeper + 30-day hard-delete.

Soft-deletes expired non-pinned rows. After 30 days in ``deleted_at``
state, rows are hard-deleted with cascade (memory_scopes, memory_uses).
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import Memory, MemoryScope, MemoryUse

logger = logging.getLogger(__name__)


async def sweep_expired(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Soft-delete non-pinned, non-deleted rows whose expires_at < now."""
    now = now or datetime.utcnow()
    res = await session.execute(
        update(Memory)
        .where(
            and_(
                Memory.expires_at.is_not(None),
                Memory.expires_at < now,
                Memory.deleted_at.is_(None),
                Memory.pinned.is_(False),
            )
        )
        .values(deleted_at=now)
    )
    await session.flush()
    count = int(res.rowcount or 0)
    if count:
        try:
            from ai_portal.control_plane import emit_audit

            emit_audit(event_type="memory.sweep.expired", resource={"count": count})
        except Exception:
            pass
    return count


async def purge_old_deleted(
    session: AsyncSession, *, now: datetime | None = None, retention_days: int = 30
) -> int:
    """Hard-delete rows soft-deleted more than ``retention_days`` ago.

    Cascade clears ``memory_scopes`` and ``memory_uses``.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=retention_days)
    ids = (
        await session.execute(
            select(Memory.id).where(
                Memory.deleted_at.is_not(None), Memory.deleted_at < cutoff
            )
        )
    ).scalars().all()
    if not ids:
        return 0
    # cascade is wired through FK ondelete=CASCADE so a single delete works
    await session.execute(delete(MemoryUse).where(MemoryUse.memory_id.in_(ids)))
    await session.execute(delete(MemoryScope).where(MemoryScope.memory_id.in_(ids)))
    res = await session.execute(delete(Memory).where(Memory.id.in_(ids)))
    await session.flush()
    return int(res.rowcount or len(ids))


async def run_once(session: AsyncSession) -> dict[str, int]:
    """Run a single sweep cycle. Returns counts for observability."""
    return {
        "expired": await sweep_expired(session),
        "purged": await purge_old_deleted(session),
    }
