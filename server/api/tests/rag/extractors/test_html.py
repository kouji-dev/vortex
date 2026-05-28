"""HTML extractor tests — depends only on beautifulsoup4 (already pinned)."""
from __future__ import annotations

import pytest

from ai_portal.rag.extractors.html import HtmlExtractor

_SAMPLE = b"""<!doctype html>
<html>
  <head><title>Acme Docs</title></head>
  <body>
    <nav>main nav junk</nav>
    <article>
      <h1>Welcome</h1>
      <p>This is the intro paragraph with real content for the article body.</p>
      <h2>Section</h2>
      <p>Section body that explains the subject in additional detail.</p>
    </article>
    <script>var noise = 1;</script>
  </body>
</html>"""


@pytest.mark.asyncio
async def test_html_extracts_title_and_headings():
    doc = await HtmlExtractor().extract(_SAMPLE, meta={})
    assert doc.meta["title"] == "Acme Docs"
    heads = [(b.text, b.level) for b in doc.blocks if b.kind == "heading"]
    assert ("Welcome", 1) in heads
    assert ("Section", 2) in heads


@pytest.mark.asyncio
async def test_html_strips_script_and_nav():
    doc = await HtmlExtractor().extract(_SAMPLE, meta={})
    flat = "\n".join(b.text for b in doc.blocks)
    assert "noise" not in flat
    assert "main nav junk" not in flat
