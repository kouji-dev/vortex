"""Structural chunker — splits at heading boundaries.

``meta["heading_path"]`` carries the running list of ancestor headings
(``["Intro", "Goals"]``) so retrieval can show breadcrumb context.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from ai_portal.rag.chunkers.protocol import Chunk, ChunkOpts, count_tokens
from ai_portal.rag.extractors.protocol import (
    ExtractedDocument,
    HeadingBlock,
    ParagraphBlock,
    TableBlock,
)


class StructuralChunker:
    name = "structural"

    async def chunk(
        self, doc: ExtractedDocument, opts: ChunkOpts
    ) -> AsyncIterator[Chunk]:
        path: list[str] = []
        max_t = max(1, opts.max_tokens)
        buf: list[str] = []
        tok = 0
        idx = 0

        def make_chunk(text: str, n: int) -> Chunk:
            return Chunk(
                text=text,
                index=n,
                token_count=count_tokens(text),
                meta={
                    "chunker": StructuralChunker.name,
                    "heading_path": list(path),
                },
            )

        for blk in doc.blocks:
            if isinstance(blk, HeadingBlock):
                # Flush any buffered prose under the prior heading.
                if buf:
                    joined = "\n".join(buf)
                    yield make_chunk(joined, idx)
                    idx += 1
                    buf, tok = [], 0
                # Maintain a stack-of-headings by level.
                level = max(1, blk.level)
                path = path[: level - 1]
                path.append(blk.text)
                continue
            if isinstance(blk, ParagraphBlock):
                t = blk.text
            elif isinstance(blk, TableBlock):
                t = "\n".join("\t".join(r) for r in blk.rows)
            else:
                t = getattr(blk, "text", "") or ""
            if not t:
                continue
            tc = count_tokens(t)
            if buf and tok + tc > max_t:
                joined = "\n".join(buf)
                yield make_chunk(joined, idx)
                idx += 1
                buf, tok = [], 0
            buf.append(t)
            tok += tc
        if buf:
            joined = "\n".join(buf)
            yield make_chunk(joined, idx)


__all__ = ["StructuralChunker"]
