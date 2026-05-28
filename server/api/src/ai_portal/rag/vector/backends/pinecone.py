"""Pinecone backend wrapper.

Uses the ``pinecone`` (v5) client if installed; HTTP semantics are wrapped
with ``asyncio.to_thread`` since the SDK is sync. Filters are translated
to Pinecone metadata-filter syntax.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ai_portal.rag.vector.protocol import (
    VectorFilter,
    VectorHit,
    VectorPoint,
)


def _flt_to_pinecone(flt: VectorFilter | None) -> dict | None:
    if flt is None or flt.is_empty():
        return None
    clauses: list[dict] = []
    if flt.must:
        for k, v in flt.must.items():
            clauses.append({k: {"$eq": v}})
    if flt.must_not:
        for k, v in flt.must_not.items():
            clauses.append({k: {"$ne": v}})
    if flt.range:
        for k, spec in flt.range.items():
            sub: dict = {}
            if "gte" in spec:
                sub["$gte"] = spec["gte"]
            if "gt" in spec:
                sub["$gt"] = spec["gt"]
            if "lte" in spec:
                sub["$lte"] = spec["lte"]
            if "lt" in spec:
                sub["$lt"] = spec["lt"]
            clauses.append({k: sub})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


@dataclass
class PineconeStore:
    name: str = "pinecone"
    pc: Any = None
    cloud: str = "aws"
    region: str = "us-east-1"

    def _index(self, ns: str):
        return self.pc.Index(ns)

    async def ensure_namespace(self, ns: str, dim: int) -> None:
        def _do() -> None:
            existing = {i.name for i in self.pc.list_indexes()}
            if ns not in existing:
                from pinecone import ServerlessSpec  # type: ignore

                self.pc.create_index(
                    name=ns,
                    dimension=dim,
                    metric="cosine",
                    spec=ServerlessSpec(cloud=self.cloud, region=self.region),
                )

        await asyncio.to_thread(_do)

    async def upsert(self, ns: str, points: list[VectorPoint]) -> None:
        if not points:
            return

        def _do() -> None:
            idx = self._index(ns)
            # batch at 100 per Pinecone limit
            batch_size = 100
            for i in range(0, len(points), batch_size):
                chunk = points[i : i + batch_size]
                idx.upsert(
                    vectors=[
                        {"id": p.id, "values": p.embedding, "metadata": p.payload}
                        for p in chunk
                    ]
                )

        await asyncio.to_thread(_do)

    async def delete(self, ns: str, ids: list[str]) -> None:
        if not ids:
            return

        def _do() -> None:
            self._index(ns).delete(ids=list(ids))

        await asyncio.to_thread(_do)

    async def query(
        self,
        ns: str,
        vec: list[float],
        top_k: int,
        flt: VectorFilter | None = None,
    ) -> list[VectorHit]:
        def _do() -> list[VectorHit]:
            res = self._index(ns).query(
                vector=vec,
                top_k=top_k,
                filter=_flt_to_pinecone(flt),
                include_metadata=True,
            )
            matches = res.get("matches") if isinstance(res, dict) else res.matches
            return [
                VectorHit(
                    id=str(m["id"] if isinstance(m, dict) else m.id),
                    score=float(m["score"] if isinstance(m, dict) else m.score),
                    payload=(m.get("metadata") if isinstance(m, dict) else m.metadata)
                    or {},
                )
                for m in matches or []
            ]

        return await asyncio.to_thread(_do)

    async def count(self, ns: str, flt: VectorFilter | None = None) -> int:
        def _do() -> int:
            stats = self._index(ns).describe_index_stats()
            total = stats.get("total_vector_count") if isinstance(stats, dict) else getattr(
                stats, "total_vector_count", 0
            )
            return int(total or 0)

        return await asyncio.to_thread(_do)


def build(config: dict) -> PineconeStore:
    try:
        from pinecone import Pinecone  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "pinecone-client not installed; install to use the pinecone backend"
        ) from e
    pc = Pinecone(api_key=config.get("api_key", ""))
    return PineconeStore(
        pc=pc,
        cloud=config.get("cloud", "aws"),
        region=config.get("region", "us-east-1"),
    )
