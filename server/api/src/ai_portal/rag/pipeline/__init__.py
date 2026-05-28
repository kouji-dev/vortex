"""8-stage RAG ingestion pipeline.

Stages: ``fetch -> extract -> normalize -> redact -> chunk -> enrich ->
embed -> index``. Each stage emits progress + errors via injected hooks;
per-document failures are isolated and the document is quarantined while
other documents continue processing.
"""
from __future__ import annotations

from ai_portal.rag.pipeline.runner import (
    PipelineDeps,
    PipelineResult,
    PipelineRunner,
    StageCtx,
    StageError,
    StageOutcome,
)

__all__ = [
    "PipelineDeps",
    "PipelineResult",
    "PipelineRunner",
    "StageCtx",
    "StageError",
    "StageOutcome",
]
