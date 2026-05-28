"""VectorStore protocol + DTOs.

A concrete backend implements :class:`VectorStore` and registers under a
name. The pipeline writes through ``upsert`` and reads through
``query``/``count``. Filters are passed declaratively so each backend can
translate to its native predicate language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class VectorPoint:
    """Embedded document chunk + payload."""

    id: str
    embedding: list[float]
    payload: dict = field(default_factory=dict)


@dataclass
class VectorHit:
    id: str
    score: float
    payload: dict = field(default_factory=dict)


@dataclass
class VectorFilter:
    """Declarative filter spec.

    Each backend maps these to its native predicate API:

    - ``must``     : all clauses are AND'd, exact-match terms.
    - ``must_not`` : negated AND'd clauses.
    - ``range``    : numeric/date range, e.g.
      ``{"created_at": {"gte": "2026-01-01"}}``.
    """

    must: dict | None = None
    must_not: dict | None = None
    range: dict | None = None

    def is_empty(self) -> bool:
        return not (self.must or self.must_not or self.range)


@runtime_checkable
class VectorStore(Protocol):
    """Common contract for pluggable vector backends."""

    name: str

    async def ensure_namespace(self, ns: str, dim: int) -> None: ...
    async def upsert(self, ns: str, points: list[VectorPoint]) -> None: ...
    async def delete(self, ns: str, ids: list[str]) -> None: ...
    async def query(
        self,
        ns: str,
        vec: list[float],
        top_k: int,
        flt: VectorFilter | None = None,
    ) -> list[VectorHit]: ...
    async def count(self, ns: str, flt: VectorFilter | None = None) -> int: ...
