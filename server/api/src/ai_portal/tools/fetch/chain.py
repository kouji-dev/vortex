from __future__ import annotations

from ai_portal.tools.fetch.base import BaseFetchProvider

_MAX_CHARS = 8_000


def _truncate(text: str) -> str:
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + "\n\n[content truncated]"
    return text


class FetchChain:
    def __init__(self, providers: list[BaseFetchProvider]) -> None:
        self.providers = providers

    def fetch(self, url: str) -> tuple[str, str]:
        """Return (content, provider_name). provider_name is the winning provider or 'none'."""
        for provider in self.providers:
            result = provider.fetch(url)
            if result:
                return _truncate(result), provider.name
        return (
            f"Could not retrieve content from {url} after all strategies failed. "
            "Use search snippets and training data to answer.",
            "none",
        )
