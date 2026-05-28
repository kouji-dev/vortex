"""Stage 4 — redact.

Applies the shared PII guardrail when the KB ingest policy opts in.
``ctx.kb_settings["redactor"]`` is a callable ``async (text) -> text``
which production wiring binds to ``gateway.guardrails.redact_pii``. When
no redactor is configured the stage is a no-op.
"""
from __future__ import annotations

from ai_portal.rag.pipeline.runner import Stage, StageCtx, StageError


async def redact_stage(ctx: StageCtx) -> StageCtx:
    if ctx.extracted is None:
        raise StageError(Stage.redact, "no extracted document")
    if not ctx.kb_settings.get("redact_enabled"):
        return ctx
    redactor = ctx.kb_settings.get("redactor")
    if redactor is None:
        return ctx
    ctx.extracted.text = await redactor(ctx.extracted.text or "")
    return ctx


__all__ = ["redact_stage"]
