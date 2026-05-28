"""Stage 7 — embed.

Batches chunks through an injected embedder callable. Production wiring
points this at ``gateway.embed(texts, model=kb.embedder_id, actor=...)``.

Failures are surfaced as :class:`RetryableStageError` so the runner can
back-off-and-retry per :class:`PipelineDeps.retries`.
"""
from __future__ import annotations

from ai_portal.rag.pipeline.runner import (
    RetryableStageError,
    Stage,
    StageCtx,
    StageError,
)


async def embed_stage(ctx: StageCtx) -> StageCtx:
    if not ctx.chunks:
        ctx.embeddings = []
        return ctx
    embed_fn = ctx.kb_settings.get("embed_fn")
    if embed_fn is None:
        raise StageError(Stage.embed, "no embed_fn configured")
    batch_size = int(ctx.kb_settings.get("embed_batch_size", 64) or 64)
    embeddings: list[list[float]] = []
    for start in range(0, len(ctx.chunks), batch_size):
        batch = ctx.chunks[start : start + batch_size]
        texts = [c.text for c in batch]
        try:
            vectors = await embed_fn(texts)
        except Exception as exc:  # noqa: BLE001
            raise RetryableStageError(
                Stage.embed,
                f"embed batch failed: {exc}",
                cause=exc,
            ) from exc
        if len(vectors) != len(batch):
            raise StageError(
                Stage.embed,
                f"embed returned {len(vectors)} vectors for {len(batch)} chunks",
            )
        embeddings.extend(vectors)
    ctx.embeddings = embeddings
    return ctx


__all__ = ["embed_stage"]
