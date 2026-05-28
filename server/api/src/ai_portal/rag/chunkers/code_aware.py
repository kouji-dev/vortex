"""Code-aware chunker — one chunk per top-level function/class.

Consumes :class:`CodeBlock` units from the extractor when present.
``meta["function"]`` and ``meta["language"]`` are propagated.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from ai_portal.rag.chunkers.protocol import Chunk, ChunkOpts, count_tokens
from ai_portal.rag.extractors.protocol import (
    CodeBlock,
    ExtractedDocument,
)


class CodeAwareChunker:
    name = "code_aware"

    async def chunk(
        self, doc: ExtractedDocument, opts: ChunkOpts
    ) -> AsyncIterator[Chunk]:
        code_blocks = [b for b in doc.blocks if isinstance(b, CodeBlock)]
        if not code_blocks:
            # Fallback: emit the whole document as one chunk.
            text = doc.text or ""
            if text.strip():
                yield Chunk(
                    text=text,
                    index=0,
                    token_count=count_tokens(text),
                    meta={
                        "chunker": self.name,
                        "language": doc.meta.get("language"),
                    },
                )
            return

        idx = 0
        max_t = max(1, opts.max_tokens)
        for cb in code_blocks:
            tc = count_tokens(cb.text)
            if tc <= max_t:
                yield Chunk(
                    text=cb.text,
                    index=idx,
                    token_count=tc,
                    meta={
                        "chunker": self.name,
                        "language": cb.language,
                        "function": cb.function,
                    },
                )
                idx += 1
                continue
            # Oversized function — sub-split by line groups under budget.
            lines = cb.text.splitlines(keepends=True)
            buf: list[str] = []
            tok = 0
            for ln in lines:
                ltc = count_tokens(ln)
                if buf and tok + ltc > max_t:
                    chunk_text = "".join(buf)
                    yield Chunk(
                        text=chunk_text,
                        index=idx,
                        token_count=count_tokens(chunk_text),
                        meta={
                            "chunker": self.name,
                            "language": cb.language,
                            "function": cb.function,
                            "partial": True,
                        },
                    )
                    idx += 1
                    buf, tok = [], 0
                buf.append(ln)
                tok += ltc
            if buf:
                chunk_text = "".join(buf)
                yield Chunk(
                    text=chunk_text,
                    index=idx,
                    token_count=count_tokens(chunk_text),
                    meta={
                        "chunker": self.name,
                        "language": cb.language,
                        "function": cb.function,
                        "partial": True,
                    },
                )
                idx += 1


__all__ = ["CodeAwareChunker"]
