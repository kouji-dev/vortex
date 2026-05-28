"""Chunker registry — resolves chunkers by stable id (string)."""
from __future__ import annotations

import logging

from ai_portal.rag.chunkers.protocol import Chunker, NoChunker

logger = logging.getLogger(__name__)


class ChunkerRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, Chunker] = {}

    def register(self, chunker: Chunker) -> None:
        name = getattr(chunker, "name", None)
        if not name:
            raise ValueError("chunker must define .name")
        if name in self._by_name:
            raise ValueError(f"chunker name already registered: {name!r}")
        self._by_name[name] = chunker

    def resolve(self, name: str) -> Chunker:
        c = self._by_name.get(name)
        if c is None:
            raise NoChunker(f"no chunker registered with id {name!r}")
        return c

    def names(self) -> list[str]:
        return sorted(self._by_name)


_default = ChunkerRegistry()


def default_registry() -> ChunkerRegistry:
    return _default


def register_builtins(registry: ChunkerRegistry | None = None) -> ChunkerRegistry:
    """Register the 5 bundled chunkers (fixed_token, sentence, semantic, structural, code_aware)."""
    reg = registry or _default
    from ai_portal.rag.chunkers.code_aware import CodeAwareChunker
    from ai_portal.rag.chunkers.fixed_token import FixedTokenChunker
    from ai_portal.rag.chunkers.semantic import SemanticChunker
    from ai_portal.rag.chunkers.sentence import SentenceChunker
    from ai_portal.rag.chunkers.structural import StructuralChunker

    for c in (
        FixedTokenChunker(),
        SentenceChunker(),
        SemanticChunker(),
        StructuralChunker(),
        CodeAwareChunker(),
    ):
        if c.name in reg._by_name:
            continue
        try:
            reg.register(c)
        except ValueError as exc:
            logger.warning(
                "chunker_register_skip", extra={"name": c.name, "err": str(exc)}
            )
    return reg


__all__ = ["ChunkerRegistry", "default_registry", "register_builtins"]
