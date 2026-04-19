from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published_date: str | None = field(default=None)


class BaseSearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Search and return up to num_results results."""

    @property
    def name(self) -> str:
        return type(self).__name__
