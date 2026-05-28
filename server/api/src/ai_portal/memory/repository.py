"""Repository for the pluggable memory subsystem.

Thin async wrapper around SQLAlchemy that hides scope-aware queries from
the service layer. Methods return ORM rows so callers can re-use them
with the same session.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import (
    Memory,
    MemoryScope,
    MemoryType,
    MemoryUse,
    ScopeKind,
)


class MemoryRepo:
    """Scope-aware memory persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    # ── core CRUD ────────────────────────────────────────────────────

    async def add(self, m: Memory) -> Memory:
        self.s.add(m)
        await self.s.flush()
        return m

    async def get(self, mid: _uuid.UUID | str) -> Memory | None:
        if isinstance(mid, str):
            mid = _uuid.UUID(mid)
        res = await self.s.execute(select(Memory).where(Memory.id == mid))
        return res.scalar_one_or_none()

    async def soft_delete(self, mid: _uuid.UUID | str) -> None:
        if isinstance(mid, str):
            mid = _uuid.UUID(mid)
        await self.s.execute(
            update(Memory).where(Memory.id == mid).values(deleted_at=datetime.utcnow())
        )
        await self.s.flush()

    async def restore(self, mid: _uuid.UUID | str) -> None:
        if isinstance(mid, str):
            mid = _uuid.UUID(mid)
        await self.s.execute(
            update(Memory).where(Memory.id == mid).values(deleted_at=None)
        )
        await self.s.flush()

    async def patch(self, mid: _uuid.UUID | str, **fields: Any) -> None:
        if not fields:
            return
        if isinstance(mid, str):
            mid = _uuid.UUID(mid)
        await self.s.execute(update(Memory).where(Memory.id == mid).values(**fields))
        await self.s.flush()

    # ── scope-aware listing ─────────────────────────────────────────

    async def list_for_actor(
        self,
        *,
        org_id: _uuid.UUID,
        actor_user_id: int | str,
        team_ids: list[str] | None = None,
        assistant_id: str | None = None,
        conversation_id: int | str | None = None,
        type: MemoryType | None = None,
        q: str | None = None,
        include_deleted: bool = False,
        limit: int = 200,
    ) -> list[Memory]:
        team_ids = team_ids or []
        clauses: list[Any] = [Memory.org_id == org_id]
        if not include_deleted:
            clauses.append(Memory.deleted_at.is_(None))

        actor_user_str = str(actor_user_id)
        scope_or = [
            and_(
                Memory.scope_kind == ScopeKind.user,
                Memory.scope_ids_json.cast(JSONB).contains([actor_user_str]),
            ),
            and_(
                Memory.scope_kind == ScopeKind.org,
                Memory.scope_ids_json.cast(JSONB).contains([str(org_id)]),
            ),
        ]
        for tid in team_ids:
            scope_or.append(
                and_(
                    Memory.scope_kind == ScopeKind.team,
                    Memory.scope_ids_json.cast(JSONB).contains([str(tid)]),
                )
            )
        if assistant_id:
            scope_or.append(
                and_(
                    Memory.scope_kind == ScopeKind.assistant,
                    Memory.scope_ids_json.cast(JSONB).contains([str(assistant_id)]),
                )
            )
        if conversation_id is not None:
            scope_or.append(
                and_(
                    Memory.scope_kind == ScopeKind.conversation,
                    Memory.scope_ids_json.cast(JSONB).contains([str(conversation_id)]),
                )
            )
        clauses.append(or_(*scope_or))

        if type is not None:
            clauses.append(Memory.type == type)
        if q:
            clauses.append(Memory.text.ilike(f"%{q}%"))

        stmt = select(Memory).where(and_(*clauses)).limit(limit)
        rows = await self.s.execute(stmt)
        return list(rows.scalars())

    # ── vector search ────────────────────────────────────────────────

    async def vector_search(
        self,
        *,
        org_id: _uuid.UUID,
        embedding: list[float],
        limit: int = 20,
        type: MemoryType | None = None,
    ) -> list[tuple[Memory, float]]:
        """Cosine-distance ordered candidates within the org.

        Caller is responsible for further scope filtering.
        """
        clauses: list[Any] = [
            Memory.org_id == org_id,
            Memory.deleted_at.is_(None),
            Memory.embedding.isnot(None),
        ]
        if type is not None:
            clauses.append(Memory.type == type)
        dist = Memory.embedding.cosine_distance(embedding).label("dist")
        stmt = (
            select(Memory, dist)
            .where(and_(*clauses))
            .order_by("dist")
            .limit(limit)
        )
        rows = await self.s.execute(stmt)
        return [(m, float(d)) for m, d in rows.all()]

    # ── uses / provenance ───────────────────────────────────────────

    async def record_use(
        self,
        *,
        memory_id: _uuid.UUID | str,
        query_text_hash: str,
        response_message_id: str,
        score: float,
    ) -> MemoryUse:
        if isinstance(memory_id, str):
            memory_id = _uuid.UUID(memory_id)
        row = MemoryUse(
            memory_id=memory_id,
            query_text_hash=query_text_hash,
            response_message_id=response_message_id,
            score=score,
        )
        self.s.add(row)
        await self.s.execute(
            update(Memory).where(Memory.id == memory_id).values(last_used_at=datetime.utcnow())
        )
        await self.s.flush()
        return row

    async def list_uses(self, mid: _uuid.UUID | str, limit: int = 100) -> list[MemoryUse]:
        if isinstance(mid, str):
            mid = _uuid.UUID(mid)
        res = await self.s.execute(
            select(MemoryUse).where(MemoryUse.memory_id == mid).order_by(MemoryUse.ts.desc()).limit(limit)
        )
        return list(res.scalars())

    # ── bulk ops ────────────────────────────────────────────────────

    async def bulk_soft_delete(self, ids: list[_uuid.UUID | str]) -> int:
        norm = [_uuid.UUID(i) if isinstance(i, str) else i for i in ids]
        if not norm:
            return 0
        res = await self.s.execute(
            update(Memory).where(Memory.id.in_(norm)).values(deleted_at=datetime.utcnow())
        )
        await self.s.flush()
        return int(res.rowcount or 0)

    async def hard_delete(self, ids: list[_uuid.UUID | str]) -> int:
        norm = [_uuid.UUID(i) if isinstance(i, str) else i for i in ids]
        if not norm:
            return 0
        res = await self.s.execute(delete(Memory).where(Memory.id.in_(norm)))
        await self.s.flush()
        return int(res.rowcount or 0)

    # ── scope denorm ─────────────────────────────────────────────────

    async def write_scopes(self, m: Memory) -> None:
        """Mirror Memory.scope_ids_json into the denormalised memory_scopes table."""
        await self.s.execute(
            delete(MemoryScope).where(MemoryScope.memory_id == m.id)
        )
        for sid in m.scope_ids_json or []:
            self.s.add(
                MemoryScope(memory_id=m.id, scope_kind=m.scope_kind, scope_id=str(sid))
            )
        await self.s.flush()
