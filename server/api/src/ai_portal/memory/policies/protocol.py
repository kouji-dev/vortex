"""MemoryPolicy protocol — extract/recall gating + sensitive-category match."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_portal.memory.extractors.protocol import ExtractScope, Turn
from ai_portal.memory.recallers.protocol import RecallScope


@runtime_checkable
class MemoryPolicy(Protocol):
    name: str

    async def should_extract(self, turn: Turn, scope: ExtractScope) -> bool: ...

    async def should_recall(self, query: str, scope: RecallScope) -> bool: ...

    async def sensitive_category_match(self, text: str) -> list[str]:
        """Return the list of sensitive categories matched by ``text``.

        Empty list = clean. Non-empty = service must drop / redact / audit.
        """
        ...
