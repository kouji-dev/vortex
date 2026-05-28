"""In-memory vector backend.

Used for tests and as a reference implementation. Stores points in a dict
keyed by ``(namespace, id)`` and ranks by cosine similarity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ai_portal.rag.vector.protocol import (
    VectorFilter,
    VectorHit,
    VectorPoint,
    VectorStore,
)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _matches(payload: dict, flt: VectorFilter | None) -> bool:
    if flt is None or flt.is_empty():
        return True
    if flt.must:
        for k, v in flt.must.items():
            if payload.get(k) != v:
                return False
    if flt.must_not:
        for k, v in flt.must_not.items():
            if payload.get(k) == v:
                return False
    if flt.range:
        for k, spec in flt.range.items():
            val = payload.get(k)
            if val is None:
                return False
            if "gte" in spec and val < spec["gte"]:
                return False
            if "gt" in spec and val <= spec["gt"]:
                return False
            if "lte" in spec and val > spec["lte"]:
                return False
            if "lt" in spec and val >= spec["lt"]:
                return False
    return True


@dataclass
class MemoryVectorStore:
    name: str = "memory"
    _dims: dict[str, int] = field(default_factory=dict)
    _points: dict[tuple[str, str], VectorPoint] = field(default_factory=dict)

    async def ensure_namespace(self, ns: str, dim: int) -> None:
        existing = self._dims.get(ns)
        if existing is not None and existing != dim:
            raise ValueError(f"namespace {ns!r} already registered with dim={existing}")
        self._dims[ns] = dim

    async def upsert(self, ns: str, points: list[VectorPoint]) -> None:
        for p in points:
            self._points[(ns, p.id)] = p

    async def delete(self, ns: str, ids: list[str]) -> None:
        for pid in ids:
            self._points.pop((ns, pid), None)

    async def query(
        self,
        ns: str,
        vec: list[float],
        top_k: int,
        flt: VectorFilter | None = None,
    ) -> list[VectorHit]:
        scored: list[VectorHit] = []
        for (point_ns, _pid), point in self._points.items():
            if point_ns != ns:
                continue
            if not _matches(point.payload, flt):
                continue
            score = _cosine(vec, point.embedding)
            scored.append(VectorHit(id=point.id, score=score, payload=point.payload))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

    async def count(self, ns: str, flt: VectorFilter | None = None) -> int:
        total = 0
        for (point_ns, _pid), point in self._points.items():
            if point_ns != ns:
                continue
            if _matches(point.payload, flt):
                total += 1
        return total


def build(config: dict) -> MemoryVectorStore:
    return MemoryVectorStore()
