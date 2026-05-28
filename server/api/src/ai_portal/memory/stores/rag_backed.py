"""rag_backed store — delegate persistence to a hidden RAG KB.

When an org wants unified retrieval across documents + memories, the
``rag_backed`` store ingests each memory as a chunk in a hidden knowledge
base named ``memories:<org_id>`` and retrieves via the RAG facade. The
canonical ``memories`` table is still updated by ``MemoryRepo`` so the
provenance + lifecycle paths stay intact.

The actual RAG facade is imported lazily — the store only needs it at
runtime, and tests stub it out by monkeypatching ``_rag``.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import Memory
from ai_portal.memory.repository import MemoryRepo

from .registry import register

logger = logging.getLogger(__name__)


def _hidden_kb_name(org_id: Any) -> str:
    return f"memories:{org_id}"


def _rag() -> Any:
    """Late-bound import of the RAG facade.

    Returns ``None`` if the RAG module is not wired in this deployment so
    the store can degrade to ``postgres_default`` behaviour without
    raising.
    """
    try:
        from ai_portal import rag as rag_mod  # type: ignore

        return rag_mod
    except Exception:
        return None


class RagBackedStore:
    name = "rag_backed"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = MemoryRepo(session)

    async def upsert(self, memory: Memory) -> Memory:
        if memory.id is None:
            await self.repo.add(memory)
        else:
            existing = await self.repo.get(memory.id)
            if existing is None:
                await self.repo.add(memory)
            else:
                await self.repo.patch(
                    memory.id,
                    text=memory.text,
                    importance=memory.importance,
                    confidence=memory.confidence,
                    tags_json=memory.tags_json,
                    pinned=memory.pinned,
                )

        rag = _rag()
        if rag is not None:
            ingest = getattr(rag, "ingest_memory_chunk", None)
            if ingest is not None:
                try:
                    await ingest(
                        kb_name=_hidden_kb_name(memory.org_id),
                        memory_id=str(memory.id),
                        text=memory.text,
                        meta={
                            "type": getattr(memory.type, "value", str(memory.type)),
                            "scope_kind": getattr(
                                memory.scope_kind, "value", str(memory.scope_kind)
                            ),
                            "tags": memory.tags_json,
                        },
                    )
                except Exception:
                    logger.exception("memory.rag_backed.ingest_failed")
        return memory

    async def delete(self, memory_id: str) -> None:
        await self.repo.soft_delete(memory_id)
        rag = _rag()
        if rag is not None:
            drop = getattr(rag, "drop_memory_chunk", None)
            if drop is not None:
                try:
                    await drop(memory_id=memory_id)
                except Exception:
                    logger.exception("memory.rag_backed.drop_failed")

    async def list_for_actor(
        self,
        *,
        org_id: Any,
        actor_user_id: str | int,
        team_ids: list[str] | None = None,
        **kw: Any,
    ) -> list[Memory]:
        org_uuid = org_id if isinstance(org_id, _uuid.UUID) else _uuid.UUID(str(org_id))
        return await self.repo.list_for_actor(
            org_id=org_uuid,
            actor_user_id=actor_user_id,
            team_ids=team_ids,
            **{k: v for k, v in kw.items() if k in {"assistant_id", "conversation_id", "type", "q", "limit"}},
        )

    async def search(
        self,
        *,
        org_id: Any,
        embedding: list[float],
        limit: int = 20,
        query: str | None = None,
        **_: Any,
    ) -> list[tuple[Memory, float]]:
        rag = _rag()
        retrieve = getattr(rag, "retrieve_memory_chunks", None) if rag else None
        if retrieve is not None and query is not None:
            try:
                hits = await retrieve(
                    kb_name=_hidden_kb_name(org_id), query=query, limit=limit
                )
            except Exception:
                logger.exception("memory.rag_backed.retrieve_failed")
                hits = []
            results: list[tuple[Memory, float]] = []
            for h in hits:
                mid = getattr(h, "memory_id", None) or (h.get("memory_id") if isinstance(h, dict) else None)
                score = getattr(h, "score", None) if not isinstance(h, dict) else h.get("score")
                if not mid:
                    continue
                row = await self.repo.get(mid)
                if row is not None:
                    results.append((row, 1.0 - float(score or 0.0)))
            if results:
                return results
        # fall back to pgvector
        org_uuid = org_id if isinstance(org_id, _uuid.UUID) else _uuid.UUID(str(org_id))
        return await self.repo.vector_search(
            org_id=org_uuid, embedding=embedding, limit=limit
        )


def make_rag_backed(session: AsyncSession) -> RagBackedStore:
    return RagBackedStore(session)


register("rag_backed", make_rag_backed)
