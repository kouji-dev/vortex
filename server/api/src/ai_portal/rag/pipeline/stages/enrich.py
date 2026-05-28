"""Stage 6 — metadata enrich.

Fills the per-chunk meta envelope with title / author / tags drawn from
the extracted doc and from KB defaults. Idempotent — runs after redact
so PII is never echoed into chunk metadata.
"""
from __future__ import annotations

from pathlib import PurePosixPath

from ai_portal.rag.pipeline.runner import StageCtx


def _derive_title(ctx: StageCtx) -> str | None:
    if ctx.extracted is None:
        return None
    title = ctx.extracted.meta.get("title")
    if title:
        return str(title)
    if ctx.source_uri:
        try:
            return PurePosixPath(ctx.source_uri).name or ctx.source_uri
        except Exception:
            return ctx.source_uri
    return None


async def enrich_stage(ctx: StageCtx) -> StageCtx:
    if ctx.extracted is None or not ctx.chunks:
        return ctx
    title = _derive_title(ctx)
    tags = list(ctx.kb_settings.get("default_tags") or [])
    language = ctx.extracted.meta.get("language")
    source_uri = ctx.source_uri
    for c in ctx.chunks:
        c.meta.setdefault("title", title)
        c.meta.setdefault("source_uri", source_uri)
        c.meta.setdefault("kb_id", ctx.kb_id)
        c.meta.setdefault("document_id", ctx.document_id)
        if language and "language" not in c.meta:
            c.meta["language"] = language
        if tags:
            existing = set(c.meta.get("tags") or [])
            c.meta["tags"] = sorted(existing | set(tags))
    return ctx


__all__ = ["enrich_stage"]
