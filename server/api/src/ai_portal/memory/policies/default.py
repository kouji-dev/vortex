"""default policy — extract + recall always allowed, no sensitive match.

The default policy is intentionally permissive; admin orgs that need
stricter behaviour pick ``strict_eu`` (or a future custom one) in
``MemoryExtractionPolicy`` / ``MemoryRecallPolicy``.
"""
from __future__ import annotations

from ai_portal.memory.extractors.protocol import ExtractScope, Turn
from ai_portal.memory.recallers.protocol import RecallScope

from .registry import register


class DefaultPolicy:
    name = "default"

    async def should_extract(self, turn: Turn, scope: ExtractScope) -> bool:
        return True

    async def should_recall(self, query: str, scope: RecallScope) -> bool:
        return True

    async def sensitive_category_match(self, text: str) -> list[str]:
        return []


register(DefaultPolicy())
