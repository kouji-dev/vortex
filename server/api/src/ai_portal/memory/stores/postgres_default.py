"""postgres_default store — thin wrapper around :class:`MemoryRepo`.

This store talks to the canonical ``memories`` table via pgvector. All
scope-aware filtering is delegated to the repository.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import Memory, MemoryType
from ai_portal.memory.repository import MemoryRepo

from .registry import register


def _coerce_org(v: Any) -> _uuid.UUID:
    return v if isinstance(v, _uuid.UUID) else _uuid.UUID(str(v))


class PostgresDefaultStore:
    name = "postgres_default"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = MemoryRepo(session)

    async def upsert(self, memory: Memory) -> Memory:
        if memory.id is None:
            return await self.repo.add(memory)
        existing = await self.repo.get(memory.id)
        if existing is None:
            return await self.repo.add(memory)
        # patch updatable fields
        patch_fields = {
            "text": memory.text,
            "importance": memory.importance,
            "confidence": memory.confidence,
            "tags_json": memory.tags_json,
            "pinned": memory.pinned,
        }
        await self.repo.patch(memory.id, **patch_fields)
        return await self.repo.get(memory.id)  # type: ignore[return-value]

    async def delete(self, memory_id: str) -> None:
        await self.repo.soft_delete(memory_id)

    async def list_for_actor(
        self,
        *,
        org_id: Any,
        actor_user_id: str | int,
        team_ids: list[str] | None = None,
        assistant_id: str | None = None,
        conversation_id: int | str | None = None,
        type: str | None = None,
        q: str | None = None,
        limit: int = 200,
        **_: Any,
    ) -> list[Memory]:
        return await self.repo.list_for_actor(
            org_id=_coerce_org(org_id),
            actor_user_id=actor_user_id,
            team_ids=team_ids,
            assistant_id=assistant_id,
            conversation_id=conversation_id,
            type=MemoryType(type) if type else None,
            q=q,
            limit=limit,
        )

    async def search(
        self,
        *,
        org_id: Any,
        embedding: list[float],
        limit: int = 20,
        type: str | None = None,
        **_: Any,
    ) -> list[tuple[Memory, float]]:
        return await self.repo.vector_search(
            org_id=_coerce_org(org_id),
            embedding=embedding,
            limit=limit,
            type=MemoryType(type) if type else None,
        )


def make_postgres_default(session: AsyncSession) -> PostgresDefaultStore:
    return PostgresDefaultStore(session)


register("postgres_default", make_postgres_default)
