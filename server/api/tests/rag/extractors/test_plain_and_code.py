"""Lightweight extractor tests that avoid heavy optional deps."""
from __future__ import annotations

import pytest

from ai_portal.rag.extractors.code import CodeExtractor
from ai_portal.rag.extractors.markdown import MarkdownExtractor
from ai_portal.rag.extractors.plain import PlainTextExtractor


@pytest.mark.asyncio
async def test_plain_text_utf8_and_latin1_roundtrip():
    ext = PlainTextExtractor()
    doc = await ext.extract("café résumé".encode("utf-8"), meta={})
    assert "café" in doc.text
    doc2 = await ext.extract("café résumé".encode("latin-1"), meta={})
    assert "caf" in doc2.text


@pytest.mark.asyncio
async def test_plain_paragraph_split():
    ext = PlainTextExtractor()
    doc = await ext.extract(b"para one\n\npara two\n\npara three", meta={})
    para_texts = [b.text for b in doc.blocks]
    assert para_texts == ["para one", "para two", "para three"]


@pytest.mark.asyncio
async def test_markdown_atx_headings_and_paragraphs():
    md = b"# Title\n\nIntro paragraph.\n\n## Goals\n\nGoal one.\n"
    doc = await MarkdownExtractor().extract(md, meta={})
    headings = [
        (b.text, b.level) for b in doc.blocks if b.kind == "heading"
    ]
    assert headings == [("Title", 1), ("Goals", 2)]
    paragraphs = [b.text for b in doc.blocks if b.kind == "paragraph"]
    assert "Intro paragraph." in paragraphs
    assert "Goal one." in paragraphs


@pytest.mark.asyncio
async def test_markdown_fenced_code_block_language():
    md = b"# Title\n\n```python\ndef foo():\n    return 1\n```\n"
    doc = await MarkdownExtractor().extract(md, meta={})
    code = [b for b in doc.blocks if b.kind == "code"]
    assert len(code) == 1
    assert code[0].language == "python"
    assert "def foo():" in code[0].text


@pytest.mark.asyncio
async def test_code_extractor_python_splits_by_function():
    src = b"def foo():\n    return 1\n\ndef bar(x):\n    return x + 1\n"
    ext = CodeExtractor()
    doc = await ext.extract(
        src,
        meta={"mime": "text/x-python", "source_uri": "thing.py"},
    )
    funcs = [b.function for b in doc.blocks if b.kind == "code"]
    assert "foo" in funcs
    assert "bar" in funcs
    assert all(
        b.language == "python" for b in doc.blocks if b.kind == "code"
    )
