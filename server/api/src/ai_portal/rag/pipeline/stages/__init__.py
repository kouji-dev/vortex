"""Bundled pipeline stage functions.

Each stage is a small ``async def stage(ctx) -> ctx`` callable. They're
exposed as a ready-to-wire dict via :func:`bundled_stages` so production
startup can do ``PipelineRunner(PipelineDeps(stages=bundled_stages()))``.
"""
from __future__ import annotations

from ai_portal.rag.pipeline.runner import Stage, StageFn
from ai_portal.rag.pipeline.stages.chunk import chunk_stage
from ai_portal.rag.pipeline.stages.embed import embed_stage
from ai_portal.rag.pipeline.stages.enrich import enrich_stage
from ai_portal.rag.pipeline.stages.extract import extract_stage
from ai_portal.rag.pipeline.stages.fetch import fetch_stage
from ai_portal.rag.pipeline.stages.index import index_stage
from ai_portal.rag.pipeline.stages.normalize import normalize_stage
from ai_portal.rag.pipeline.stages.redact import redact_stage


def bundled_stages() -> dict[Stage, StageFn]:
    """Return the default stage map. Production wiring can override any entry."""
    return {
        Stage.fetch: fetch_stage,
        Stage.extract: extract_stage,
        Stage.normalize: normalize_stage,
        Stage.redact: redact_stage,
        Stage.chunk: chunk_stage,
        Stage.enrich: enrich_stage,
        Stage.embed: embed_stage,
        Stage.index: index_stage,
    }


__all__ = [
    "bundled_stages",
    "chunk_stage",
    "embed_stage",
    "enrich_stage",
    "extract_stage",
    "fetch_stage",
    "index_stage",
    "normalize_stage",
    "redact_stage",
]
