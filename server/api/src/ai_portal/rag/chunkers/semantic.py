"""Semantic chunker — splits where adjacent sentence embeddings diverge.

The chunker requests embeddings through an injected callable so unit
tests can pass a synthetic embedder without touching the Gateway. When
no embedder is wired the chunker degrades to paragraph splits to keep
the pipeline forward-progressing.
"""
from __future__ import annotations

import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from ai_portal.rag.chunkers.protocol import Chunk, ChunkOpts, count_tokens
from ai_portal.rag.extractors.protocol import ExtractedDocument

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]

_SENT_SPLIT = re.compile(r"(?<=[\.\!\?])\s+(?=[A-Z\d\(\[\"'])")


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticChunker:
    name = "semantic"

    #: Process-wide embed function. Wired at startup; tests override.
    embed_fn: EmbedFn | None = None

    def __init__(self, embed_fn: EmbedFn | None = None) -> None:
        if embed_fn is not None:
            self.embed_fn = embed_fn

    async def _embed(self, texts: list[str]) -> list[list[float]] | None:
        fn = self.embed_fn
        if fn is None:
            return None
        try:
            return await fn(texts)
        except Exception:
            return None

    async def chunk(
        self, doc: ExtractedDocument, opts: ChunkOpts
    ) -> AsyncIterator[Chunk]:
        text = (doc.text or "").strip()
        if not text:
            return
        sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
        if not sentences:
            return
        embeddings = await self._embed(sentences)

        # Identify topical break points.
        breaks: list[int] = []
        threshold = float(opts.extra.get("similarity_break", 0.45)) if opts.extra else 0.45
        if embeddings and len(embeddings) == len(sentences):
            for i in range(1, len(sentences)):
                sim = _cosine(embeddings[i - 1], embeddings[i])
                if sim < threshold:
                    breaks.append(i)
        else:
            # Fallback: paragraph boundaries (double newline) approximated.
            for i, s in enumerate(sentences[:-1], start=1):
                if s.endswith((":", ".")) and sentences[i].istitle():
                    breaks.append(i)

        max_t = max(1, opts.max_tokens)
        idx = 0
        start = 0
        for br in breaks + [len(sentences)]:
            piece_sents = sentences[start:br]
            # Respect token budget: re-pack inside each topical group.
            buf: list[str] = []
            tok = 0
            for s in piece_sents:
                tc = count_tokens(s)
                if buf and tok + tc > max_t:
                    joined = " ".join(buf)
                    yield Chunk(
                        text=joined,
                        index=idx,
                        token_count=count_tokens(joined),
                        meta={"chunker": self.name, "topic_group": idx},
                    )
                    idx += 1
                    buf, tok = [], 0
                buf.append(s)
                tok += tc
            if buf:
                joined = " ".join(buf)
                yield Chunk(
                    text=joined,
                    index=idx,
                    token_count=count_tokens(joined),
                    meta={"chunker": self.name, "topic_group": idx},
                )
                idx += 1
            start = br


__all__ = ["SemanticChunker", "EmbedFn"]
