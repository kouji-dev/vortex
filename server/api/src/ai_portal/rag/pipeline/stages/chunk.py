"""Stage 5 — chunk.

Selects the chunker via ``ctx.kb_settings["chunker_id"]`` (default
``fixed_token``) and materialises the chunks into ``ctx.chunks``.
"""
from __future__ import annotations

from ai_portal.rag.chunkers.protocol import ChunkOpts
from ai_portal.rag.chunkers.registry import default_registry as _default
from ai_portal.rag.pipeline.runner import Stage, StageCtx, StageError


async def chunk_stage(ctx: StageCtx) -> StageCtx:
    if ctx.extracted is None:
        raise StageError(Stage.chunk, "no extracted document")
    registry = ctx.kb_settings.get("chunker_registry") or _default()
    chunker_id = ctx.kb_settings.get("chunker_id", "fixed_token")
    try:
        chunker = registry.resolve(chunker_id)
    except LookupError as exc:
        raise StageError(Stage.chunk, str(exc), cause=exc) from exc
    opts = ctx.kb_settings.get("chunk_opts") or ChunkOpts()
    chunks = []
    async for c in chunker.chunk(ctx.extracted, opts):
        chunks.append(c)
    ctx.chunks = chunks
    return ctx


__all__ = ["chunk_stage"]
