"""Qdrant backend wrapper.

Uses ``qdrant-client`` if installed. The Qdrant client itself supports an
in-process ``QdrantLocal`` mode useful for tests. If the SDK is not
available at import time, a clear runtime error is raised when ``build``
is invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_portal.rag.vector.protocol import (
    VectorFilter,
    VectorHit,
    VectorPoint,
)


def _flt_to_qdrant(flt: VectorFilter | None) -> Any | None:
    if flt is None or flt.is_empty():
        return None
    from qdrant_client import models as qm  # type: ignore

    must = []
    must_not = []
    if flt.must:
        for k, v in flt.must.items():
            must.append(qm.FieldCondition(key=k, match=qm.MatchValue(value=v)))
    if flt.must_not:
        for k, v in flt.must_not.items():
            must_not.append(qm.FieldCondition(key=k, match=qm.MatchValue(value=v)))
    if flt.range:
        for k, spec in flt.range.items():
            must.append(
                qm.FieldCondition(
                    key=k,
                    range=qm.Range(
                        gte=spec.get("gte"),
                        gt=spec.get("gt"),
                        lte=spec.get("lte"),
                        lt=spec.get("lt"),
                    ),
                )
            )
    return qm.Filter(must=must or None, must_not=must_not or None)


@dataclass
class QdrantStore:
    name: str = "qdrant"
    client: Any = None  # AsyncQdrantClient | QdrantLocal

    async def ensure_namespace(self, ns: str, dim: int) -> None:
        from qdrant_client import models as qm  # type: ignore

        existing = {c.name for c in (await self.client.get_collections()).collections}
        if ns not in existing:
            await self.client.create_collection(
                collection_name=ns,
                vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            )

    async def upsert(self, ns: str, points: list[VectorPoint]) -> None:
        if not points:
            return
        from qdrant_client import models as qm  # type: ignore

        await self.client.upsert(
            collection_name=ns,
            points=[
                qm.PointStruct(id=p.id, vector=p.embedding, payload=p.payload)
                for p in points
            ],
        )

    async def delete(self, ns: str, ids: list[str]) -> None:
        if not ids:
            return
        from qdrant_client import models as qm  # type: ignore

        await self.client.delete(
            collection_name=ns,
            points_selector=qm.PointIdsList(points=list(ids)),
        )

    async def query(
        self,
        ns: str,
        vec: list[float],
        top_k: int,
        flt: VectorFilter | None = None,
    ) -> list[VectorHit]:
        res = await self.client.search(
            collection_name=ns,
            query_vector=vec,
            limit=top_k,
            query_filter=_flt_to_qdrant(flt),
        )
        return [
            VectorHit(id=str(r.id), score=float(r.score), payload=r.payload or {})
            for r in res
        ]

    async def count(self, ns: str, flt: VectorFilter | None = None) -> int:
        res = await self.client.count(
            collection_name=ns,
            count_filter=_flt_to_qdrant(flt),
            exact=True,
        )
        return int(res.count)


def build(config: dict) -> QdrantStore:
    try:
        from qdrant_client import AsyncQdrantClient  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "qdrant-client not installed; install to use the qdrant backend"
        ) from e
    url = config.get("url")
    api_key = config.get("api_key")
    location = config.get("location")  # ":memory:" supported for tests
    if location:
        client = AsyncQdrantClient(location=location)
    else:
        client = AsyncQdrantClient(url=url, api_key=api_key)
    return QdrantStore(client=client)
