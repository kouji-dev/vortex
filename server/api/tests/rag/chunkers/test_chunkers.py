"""Tests for the bundled chunkers + registry."""
from __future__ import annotations

import pytest

from ai_portal.rag.chunkers import (
    ChunkerRegistry,
    ChunkOpts,
    NoChunker,
    register_builtins,
)
from ai_portal.rag.chunkers.code_aware import CodeAwareChunker
from ai_portal.rag.chunkers.fixed_token import FixedTokenChunker
from ai_portal.rag.chunkers.semantic import SemanticChunker
from ai_portal.rag.chunkers.sentence import SentenceChunker
from ai_portal.rag.chunkers.structural import StructuralChunker
from ai_portal.rag.extractors.protocol import (
    CodeBlock,
    ExtractedDocument,
    HeadingBlock,
    ParagraphBlock,
)


@pytest.mark.asyncio
async def test_fixed_token_respects_max_and_overlap():
    doc = ExtractedDocument(text=" ".join(["word"] * 200), blocks=[], meta={})
    chunker = FixedTokenChunker()
    chunks = [
        c async for c in chunker.chunk(doc, ChunkOpts(max_tokens=32, overlap_tokens=8))
    ]
    assert len(chunks) > 1
    # Every chunk fits the budget (word-based fallback used when tiktoken absent).
    for c in chunks:
        assert len(c.text.split()) <= 32
    # Overlap: last 8 words of chunk 0 == first 8 words of chunk 1.
    assert chunks[0].text.split()[-8:] == chunks[1].text.split()[:8]


@pytest.mark.asyncio
async def test_fixed_token_zero_overlap_is_disjoint():
    doc = ExtractedDocument(text=" ".join(["w" + str(i) for i in range(100)]), blocks=[], meta={})
    chunks = [
        c async for c in FixedTokenChunker().chunk(doc, ChunkOpts(max_tokens=20, overlap_tokens=0))
    ]
    seen = set()
    for c in chunks:
        words = c.text.split()
        for w in words:
            assert w not in seen
            seen.add(w)


@pytest.mark.asyncio
async def test_sentence_chunker_ends_on_terminator():
    txt = " ".join(f"Sentence number {i}." for i in range(30))
    doc = ExtractedDocument(text=txt, blocks=[], meta={})
    chunks = [
        c async for c in SentenceChunker().chunk(doc, ChunkOpts(max_tokens=8))
    ]
    assert chunks
    for c in chunks:
        assert c.text.rstrip().endswith((".", "!", "?"))


@pytest.mark.asyncio
async def test_structural_chunker_emits_heading_path():
    blocks = [
        HeadingBlock(text="Intro", level=1),
        ParagraphBlock(text="hello world"),
        HeadingBlock(text="Goals", level=2),
        ParagraphBlock(text="something to do"),
    ]
    doc = ExtractedDocument(text="hello world\nsomething to do", blocks=blocks, meta={})
    chunks = [
        c async for c in StructuralChunker().chunk(doc, ChunkOpts(max_tokens=1024))
    ]
    paths = [c.meta["heading_path"] for c in chunks]
    assert ["Intro"] in paths
    assert ["Intro", "Goals"] in paths


@pytest.mark.asyncio
async def test_code_aware_chunker_per_function():
    code = "def foo():\n    return 1\n"
    blocks = [
        CodeBlock(text="def foo():\n    return 1\n", language="python", function="foo"),
        CodeBlock(text="def bar(x):\n    return x + 1\n", language="python", function="bar"),
    ]
    doc = ExtractedDocument(text=code, blocks=blocks, meta={"language": "python"})
    chunks = [
        c async for c in CodeAwareChunker().chunk(doc, ChunkOpts(max_tokens=64))
    ]
    assert {c.meta.get("function") for c in chunks} == {"foo", "bar"}


@pytest.mark.asyncio
async def test_semantic_chunker_uses_injected_embedder_to_break_topics():
    sentences = [
        "Apples are red fruit.",
        "Bananas are yellow fruit.",
        "Cars have engines.",
        "Trucks transport goods.",
    ]
    text = " ".join(sentences)
    # Embedder: orthogonal vectors for the two topical groups.
    async def embed(texts):
        out = []
        for t in texts:
            if "fruit" in t:
                out.append([1.0, 0.0])
            else:
                out.append([0.0, 1.0])
        return out

    doc = ExtractedDocument(text=text, blocks=[], meta={})
    chunker = SemanticChunker(embed_fn=embed)
    chunks = [
        c async for c in chunker.chunk(
            doc, ChunkOpts(max_tokens=128, extra={"similarity_break": 0.5})
        )
    ]
    # 2 topical groups expected — one fruit, one vehicle.
    assert len(chunks) >= 2


def test_chunker_registry_resolves_builtins():
    reg = ChunkerRegistry()
    register_builtins(reg)
    for name in ("fixed_token", "sentence", "semantic", "structural", "code_aware"):
        assert reg.resolve(name).name == name


def test_chunker_registry_unknown_id_raises():
    reg = ChunkerRegistry()
    with pytest.raises(NoChunker):
        reg.resolve("nope")
