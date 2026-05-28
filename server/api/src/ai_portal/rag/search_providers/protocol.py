"""SearchProvider protocol — uniform interface for external + internal search."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class SearchProviderResult:
    """One result row from any search provider."""

    title: str
    url: str
    snippet: str
    score: float = 0.0
    published_date: str | None = None
    source: str | None = None  # internal KB id, host, etc.
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SearchProvider(Protocol):
    """Provider interface. Implementations should be safe to construct
    cheaply (lazy SDK / HTTP client init)."""

    name: str

    def search(
        self, query: str, *, num_results: int = 5, **kwargs: Any
    ) -> list[SearchProviderResult]:
        ...
