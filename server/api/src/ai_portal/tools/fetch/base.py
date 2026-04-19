from __future__ import annotations

from abc import ABC, abstractmethod


class BaseFetchProvider(ABC):
    """Fetch the text content of a URL. Return None to fall through to the next provider."""

    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def fetch(self, url: str) -> str | None:
        ...
