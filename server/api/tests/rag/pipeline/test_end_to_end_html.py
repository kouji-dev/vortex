"""End-to-end pipeline run on an HTML fixture.

Uses the bundled extractor + chunker registries, an in-memory indexer,
and a stub embedder. Verifies that all 8 stages execute and that the
indexer receives a non-empty chunk + embedding stream.
"""
from __future__ import annotations

import pytest

from ai_portal.rag.chunkers.protocol import ChunkOpts
from ai_portal.rag.chunkers.registry import (
    ChunkerRegistry,
    register_builtins as register_chunkers,
)
from ai_portal.rag.extractors.registry import (
    ExtractorRegistry,
    register_builtins as register_extractors,
)
from ai_portal.rag.pipeline.runner import (
    PipelineDeps,
    PipelineRunner,
    STAGES,
    StageCtx,
    StageOutcome,
)
from ai_portal.rag.pipeline.stages import bundled_stages

_HTML = b"""<!doctype html>
<html>
  <head><title>Sample KB Doc</title></head>
  <body>
    <article>
      <h1>Sample KB Doc</h1>
      <p>This is the first paragraph of a sample knowledge-base document.</p>
      <h2>Details</h2>
      <p>Here we describe additional details with several more sentences.
         Each sentence carries enough text to produce a meaningful chunk
         after the fixed-token chunker passes over it.</p>
    </article>
  </body>
</html>"""


@pytest.mark.asyncio
async def test_pipeline_runs_eight_stages_against_html_fixture():
    extractor_registry = ExtractorRegistry()
    register_extractors(extractor_registry)
    chunker_registry = ChunkerRegistry()
    register_chunkers(chunker_registry)

    indexed: list[dict] = []

    async def fake_embedder(texts: list[str]) -> list[list[float]]:
        # Deterministic dummy vectors so the index stage can assert lengths.
        return [[float(len(t) % 7), 1.0, 0.0] for t in texts]

    async def indexer(*, kb_id, chunks, embeddings, acl):
        indexed.append(
            {"kb_id": kb_id, "n_chunks": len(chunks), "n_emb": len(embeddings)}
        )

    ctx = StageCtx(
        job_id="job-1",
        document_id="doc-1",
        kb_id="kb-test",
        source_uri="file:///sample.html",
        mime="text/html",
        raw_bytes=_HTML,
        kb_settings={
            "extractor_registry": extractor_registry,
            "chunker_registry": chunker_registry,
            "chunker_id": "fixed_token",
            "chunk_opts": ChunkOpts(max_tokens=24, overlap_tokens=4),
            "embed_fn": fake_embedder,
            "indexer": indexer,
            "redact_enabled": False,
            "default_tags": ["fixture"],
        },
    )

    runner = PipelineRunner(
        PipelineDeps(stages=bundled_stages(), backoff_base=0.0)
    )
    result = await runner.run(ctx)

    assert result.success, result.quarantine_reason
    assert [r.stage for r in result.stages] == list(STAGES)
    assert all(r.outcome is StageOutcome.ok for r in result.stages)
    # Chunks + embeddings produced + handed to indexer.
    assert ctx.chunks, "no chunks produced"
    assert len(ctx.embeddings) == len(ctx.chunks)
    assert indexed and indexed[0]["n_chunks"] == len(ctx.chunks)
    # Enrich tagged chunks with KB defaults + propagated meta.
    assert all("fixture" in c.meta.get("tags", []) for c in ctx.chunks)
    assert all(c.meta.get("kb_id") == "kb-test" for c in ctx.chunks)
    # Normalize stage stamped a content hash.
    assert "content_hash" in ctx.extracted.meta


@pytest.mark.asyncio
async def test_pipeline_quarantines_when_unknown_mime():
    extractor_registry = ExtractorRegistry()
    register_extractors(extractor_registry)
    chunker_registry = ChunkerRegistry()
    register_chunkers(chunker_registry)

    ctx = StageCtx(
        job_id="job-2",
        document_id="doc-2",
        kb_id="kb-test",
        source_uri="file:///mystery.bin",
        mime="application/x-mystery",
        raw_bytes=b"\x00\x01\x02",
        kb_settings={
            "extractor_registry": extractor_registry,
            "chunker_registry": chunker_registry,
            "embed_fn": lambda _ts: [],
        },
    )
    runner = PipelineRunner(PipelineDeps(stages=bundled_stages()))
    res = await runner.run(ctx)
    assert not res.success
    assert "extract" in (res.quarantine_reason or "")
