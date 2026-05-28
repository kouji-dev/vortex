"""Weaviate backend wrapper.

Thin async wrapper over ``weaviate-client v4`` if installed. Filters are
translated to Weaviate ``where`` filter clauses.
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


def _flt_to_weaviate(flt: VectorFilter | None) -> Any | None:
    if flt is None or flt.is_empty():
        return None
    from weaviate.classes.query import Filter  # type: ignore

    parts: list = []
    if flt.must:
        for k, v in flt.must.items():
            parts.append(Filter.by_property(k).equal(v))
    if flt.must_not:
        for k, v in flt.must_not.items():
            parts.append(Filter.by_property(k).not_equal(v))
    if flt.range:
        for k, spec in flt.range.items():
            prop = Filter.by_property(k)
            if "gte" in spec:
                parts.append(prop.greater_or_equal(spec["gte"]))
            if "gt" in spec:
                parts.append(prop.greater_than(spec["gt"]))
            if "lte" in spec:
                parts.append(prop.less_or_equal(spec["lte"]))
            if "lt" in spec:
                parts.append(prop.less_than(spec["lt"]))
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    base = parts[0]
    for p in parts[1:]:
        base = base & p
    return base


@dataclass
class WeaviateStore:
    name: str = "weaviate"
    client: Any = None

    def _collection(self, ns: str):
        return self.client.collections.get(ns)

    async def ensure_namespace(self, ns: str, dim: int) -> None:
        def _do() -> None:
            from weaviate.classes.config import Configure, DataType, Property  # type: ignore

            if not self.client.collections.exists(ns):
                self.client.collections.create(
                    name=ns,
                    vectorizer_config=Configure.Vectorizer.none(),
                    properties=[Property(name="text", data_type=DataType.TEXT)],
                )

        await asyncio.to_thread(_do)

    async def upsert(self, ns: str, points: list[VectorPoint]) -> None:
        if not points:
            return

        def _do() -> None:
            coll = self._collection(ns)
            with coll.batch.dynamic() as batch:
                for p in points:
                    batch.add_object(
                        properties=p.payload or {},
                        uuid=p.id,
                        vector=p.embedding,
                    )

        await asyncio.to_thread(_do)

    async def delete(self, ns: str, ids: list[str]) -> None:
        if not ids:
            return

        def _do() -> None:
            coll = self._collection(ns)
            for pid in ids:
                coll.data.delete_by_id(pid)

        await asyncio.to_thread(_do)

    async def query(
        self,
        ns: str,
        vec: list[float],
        top_k: int,
        flt: VectorFilter | None = None,
    ) -> list[VectorHit]:
        def _do() -> list[VectorHit]:
            coll = self._collection(ns)
            res = coll.query.near_vector(
                near_vector=vec,
                limit=top_k,
                filters=_flt_to_weaviate(flt),
                return_metadata=["distance"],
            )
            out: list[VectorHit] = []
            for o in res.objects:
                dist = getattr(o.metadata, "distance", None) or 0.0
                out.append(
                    VectorHit(
                        id=str(o.uuid),
                        score=1.0 - float(dist),
                        payload=dict(o.properties or {}),
                    )
                )
            return out

        return await asyncio.to_thread(_do)

    async def count(self, ns: str, flt: VectorFilter | None = None) -> int:
        def _do() -> int:
            coll = self._collection(ns)
            agg = coll.aggregate.over_all(filters=_flt_to_weaviate(flt))
            return int(getattr(agg, "total_count", 0) or 0)

        return await asyncio.to_thread(_do)


def build(config: dict) -> WeaviateStore:
    try:
        import weaviate  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "weaviate-client not installed; install to use the weaviate backend"
        ) from e
    url = config.get("url", "http://localhost:8080")
    api_key = config.get("api_key")
    if api_key:
        client = weaviate.connect_to_wcs(cluster_url=url, auth_credentials=weaviate.auth.AuthApiKey(api_key))
    else:
        client = weaviate.connect_to_local(host=url)
    return WeaviateStore(client=client)
