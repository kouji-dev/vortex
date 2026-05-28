"""Compaction worker — merge near-duplicate memories.

Algo: for each non-deleted, non-pinned memory, vector-search siblings in
the same scope+type. Cosine > 0.95 → merge into newest, sum importance
(clamped to 1.0), union source_turn_ids, soft-delete the older row.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import Memory, MemoryType
from ai_portal.memory.repository import MemoryRepo

logger = logging.getLogger(__name__)


async def compact_org(
    session: AsyncSession,
    org_id: _uuid.UUID,
    *,
    threshold: float = 0.95,
    now: datetime | None = None,
) -> int:
    """Walk org memories + merge near-duplicates. Returns merge count."""
    now = now or datetime.utcnow()
    repo = MemoryRepo(session)
    rows = (
        await session.execute(
            select(Memory).where(
                and_(
                    Memory.org_id == org_id,
                    Memory.deleted_at.is_(None),
                    Memory.pinned.is_(False),
                    Memory.embedding.is_not(None),
                )
            )
        )
    ).scalars().all()
    seen: set[_uuid.UUID] = set()
    merges = 0
    for m in rows:
        if m.id in seen:
            continue
        candidates = await repo.vector_search(
            org_id=org_id,
            embedding=list(m.embedding) if m.embedding is not None else [],
            limit=5,
            type=m.type,
        )
        for other, dist in candidates:
            if other.id == m.id or other.id in seen:
                continue
            if other.scope_kind != m.scope_kind:
                continue
            if set(map(str, other.scope_ids_json or [])) != set(
                map(str, m.scope_ids_json or [])
            ):
                continue
            similarity = 1.0 - dist
            if similarity < threshold:
                continue
            # newer wins as the keeper
            keeper, loser = (m, other) if m.created_at >= other.created_at else (other, m)
            new_importance = min(
                1.0, float(keeper.importance or 0.0) + float(loser.importance or 0.0)
            )
            merged_turns = list(
                {*(keeper.source_turn_ids_json or []), *(loser.source_turn_ids_json or [])}
            )
            merged_tags = list({*(keeper.tags_json or []), *(loser.tags_json or [])})
            await session.execute(
                update(Memory)
                .where(Memory.id == keeper.id)
                .values(
                    importance=new_importance,
                    source_turn_ids_json=merged_turns,
                    tags_json=merged_tags,
                )
            )
            await session.execute(
                update(Memory).where(Memory.id == loser.id).values(deleted_at=now)
            )
            seen.add(loser.id)
            merges += 1
        seen.add(m.id)
    await session.flush()
    return merges
