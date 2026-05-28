"""Stage 2 — extract.

Dispatches ``ctx.raw_bytes`` through the extractor registry by
``ctx.mime``. The registry can be overridden via ``ctx.kb_settings["extractor_registry"]``.
"""
from __future__ import annotations

from ai_portal.rag.extractors.registry import default_registry as _default
from ai_portal.rag.pipeline.runner import Stage, StageCtx, StageError


async def extract_stage(ctx: StageCtx) -> StageCtx:
    if ctx.raw_bytes is None:
        raise StageError(Stage.extract, "no raw_bytes — fetch stage must run first")
    registry = ctx.kb_settings.get("extractor_registry") or _default()
    try:
        doc = await registry.extract(
            ctx.raw_bytes,
            mime=ctx.mime or "application/octet-stream",
            meta={
                "source_uri": ctx.source_uri,
                "mime": ctx.mime,
                **(ctx.meta or {}),
            },
        )
    except LookupError as exc:
        raise StageError(Stage.extract, str(exc), cause=exc) from exc
    ctx.extracted = doc
    return ctx


__all__ = ["extract_stage"]
