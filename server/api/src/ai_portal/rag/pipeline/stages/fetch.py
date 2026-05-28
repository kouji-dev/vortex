"""Stage 1 — fetch.

Reads raw bytes for the document. If ``ctx.raw_bytes`` is already set
(connector-staged path / direct upload) the stage is a no-op. Otherwise
the runner expects ``ctx.kb_settings["fetcher"]`` to expose an async
``fetch(source_uri) -> bytes`` callable.
"""
from __future__ import annotations

from ai_portal.rag.pipeline.runner import StageCtx, StageError, Stage


async def fetch_stage(ctx: StageCtx) -> StageCtx:
    if ctx.raw_bytes is not None:
        return ctx
    fetcher = ctx.kb_settings.get("fetcher")
    if fetcher is None:
        raise StageError(Stage.fetch, "no raw_bytes and no fetcher configured")
    if not ctx.source_uri:
        raise StageError(Stage.fetch, "ctx.source_uri is required")
    data = await fetcher(ctx.source_uri)
    ctx.raw_bytes = data
    return ctx


__all__ = ["fetch_stage"]
