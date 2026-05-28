"""Tests for extractor protocol + registry dispatch."""
from __future__ import annotations

import pytest

from ai_portal.rag.extractors import (
    ExtractorRegistry,
    NoExtractor,
    ParagraphBlock,
    register_builtins,
)
from ai_portal.rag.extractors.plain import PlainTextExtractor
from ai_portal.rag.extractors.protocol import ExtractedDocument


class _FakeExt:
    name = "fake"
    mime_types = {"application/x-fake"}

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    async def extract(self, data, meta):
        return ExtractedDocument(
            text="ok", blocks=[ParagraphBlock(text="ok")], meta={"src": "fake"}
        )


def test_register_and_resolve_exact_mime():
    reg = ExtractorRegistry()
    fake = _FakeExt()
    reg.register(fake)
    assert reg.resolve("application/x-fake") is fake
    assert reg.get("fake") is fake


def test_unknown_mime_raises_no_extractor():
    reg = ExtractorRegistry()
    with pytest.raises(NoExtractor):
        reg.resolve("application/never-heard-of")


def test_duplicate_name_rejected():
    reg = ExtractorRegistry()
    reg.register(_FakeExt())
    with pytest.raises(ValueError):
        reg.register(_FakeExt())


def test_wildcard_mime_match_via_plain():
    reg = ExtractorRegistry()
    reg.register(PlainTextExtractor())
    # text/* wildcard binds — any unknown text/X type resolves to plain.
    assert reg.resolve("text/csv").name == "plain"


def test_strips_mime_parameters():
    reg = ExtractorRegistry()
    reg.register(_FakeExt())
    assert reg.resolve("application/x-fake; charset=utf-8").name == "fake"


@pytest.mark.asyncio
async def test_register_builtins_idempotent_and_dispatches_plain_text():
    reg = ExtractorRegistry()
    register_builtins(reg)
    # Idempotent — second call should not raise.
    register_builtins(reg)
    doc = await reg.extract(b"hello world\n\nsecond para", mime="text/plain")
    assert "hello world" in doc.text
    assert any(b.text == "hello world" for b in doc.blocks if hasattr(b, "text"))
