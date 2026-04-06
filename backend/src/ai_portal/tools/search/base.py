from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class BaseSearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Search and return up to num_results results."""
