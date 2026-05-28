"""Fixed-token chunker — word-based sliding window with overlap.

Uses :mod:`tiktoken` for tokenisation when present; otherwise whitespace
words. The same primitive backs ``ChunkOpts.max_tokens`` budgeting across
the codebase so behaviour stays consistent under both regimes.
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator

from ai_portal.rag.chunkers.protocol import Chunk, ChunkOpts, count_tokens
from ai_portal.rag.extractors.protocol import ExtractedDocument

_WORD_RE = re.compile(r"\S+")


class FixedTokenChunker:
    name = "fixed_token"

    async def chunk(
        self, doc: ExtractedDocument, opts: ChunkOpts
    ) -> AsyncIterator[Chunk]:
        words = _WORD_RE.findall(doc.text or "")
        if not words:
            return
        max_t = max(1, opts.max_tokens)
        overlap = max(0, min(opts.overlap_tokens, max_t - 1))
        step = max(1, max_t - overlap)
        idx = 0
        i = 0
        while i < len(words):
            window = words[i : i + max_t]
            text = " ".join(window)
            yield Chunk(
                text=text,
                index=idx,
                token_count=count_tokens(text),
                meta={"chunker": self.name, "word_offset": i},
            )
            idx += 1
            if i + max_t >= len(words):
                break
            i += step


__all__ = ["FixedTokenChunker"]
