"""Stage 8 — index.

Hands chunks + embeddings to the per-KB indexer. The indexer is an
``async (kb_id, chunks, embeddings, acl) -> None`` callable that
production wiring binds to the vector store + BM25 store + ACL store.

When no indexer is configured the stage is a no-op so unit tests that
focus on earlier stages can compose freely.
"""
from __future__ import annotations

from ai_portal.rag.pipeline.runner import Stage, StageCtx, StageError


async def index_stage(ctx: StageCtx) -> StageCtx:
    indexer = ctx.kb_settings.get("indexer")
    if indexer is None:
        return ctx
    if ctx.chunks and len(ctx.embeddings) != len(ctx.chunks):
        raise StageError(
            Stage.index,
            f"embeddings/chunks mismatch: {len(ctx.embeddings)} vs {len(ctx.chunks)}",
        )
    acl = ctx.kb_settings.get("acl")
    await indexer(
        kb_id=ctx.kb_id,
        chunks=ctx.chunks,
        embeddings=ctx.embeddings,
        acl=acl,
    )
    return ctx


__all__ = ["index_stage"]
