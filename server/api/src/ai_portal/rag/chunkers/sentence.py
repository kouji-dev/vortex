"""Sentence-aware chunker.

Splits at sentence boundaries with a regex tokeniser, then packs
sentences until the token budget would overflow. Every emitted chunk
ends on a sentence terminator (``.``, ``!``, ``?``).
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator

from ai_portal.rag.chunkers.protocol import Chunk, ChunkOpts, count_tokens
from ai_portal.rag.extractors.protocol import ExtractedDocument

_SENT_SPLIT = re.compile(r"(?<=[\.\!\?])\s+(?=[A-Z\d\(\[\"'])")


class SentenceChunker:
    name = "sentence"

    async def chunk(
        self, doc: ExtractedDocument, opts: ChunkOpts
    ) -> AsyncIterator[Chunk]:
        text = (doc.text or "").strip()
        if not text:
            return
        sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
        max_t = max(1, opts.max_tokens)
        buf: list[str] = []
        tokens_in_buf = 0
        idx = 0
        for sent in sentences:
            tc = count_tokens(sent)
            if buf and tokens_in_buf + tc > max_t:
                joined = " ".join(buf)
                yield Chunk(
                    text=joined,
                    index=idx,
                    token_count=count_tokens(joined),
                    meta={"chunker": self.name, "sentences": len(buf)},
                )
                idx += 1
                buf, tokens_in_buf = [], 0
            buf.append(sent)
            tokens_in_buf += tc
        if buf:
            joined = " ".join(buf)
            yield Chunk(
                text=joined,
                index=idx,
                token_count=count_tokens(joined),
                meta={"chunker": self.name, "sentences": len(buf)},
            )


__all__ = ["SentenceChunker"]
