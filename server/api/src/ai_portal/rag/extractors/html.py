"""HTML extractor.

Uses :mod:`readability-lxml` for boilerplate stripping when available;
falls back to a :mod:`beautifulsoup4` strip-nav/script/style pass.
"""
from __future__ import annotations

from typing import Any

from ai_portal.rag.extractors.protocol import (
    Block,
    ExtractedDocument,
    HeadingBlock,
    ParagraphBlock,
)

_NOISE_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "form")


class HtmlExtractor:
    name = "html"
    mime_types = {"text/html", "application/xhtml+xml"}

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    async def extract(self, data: bytes, meta: dict[str, Any]) -> ExtractedDocument:
        from bs4 import BeautifulSoup  # type: ignore

        raw = data.decode("utf-8", errors="replace")
        title: str | None = None

        # Title from <title> first — works regardless of readability path.
        soup_full = BeautifulSoup(raw, "html.parser")
        if soup_full.title and soup_full.title.string:
            title = soup_full.title.string.strip()

        # Try readability for cleaner body, else fall back to BS strip.
        body_html: str
        try:
            from readability import Document as ReadabilityDoc  # type: ignore

            rd = ReadabilityDoc(raw)
            body_html = rd.summary(html_partial=True)
            if not title:
                try:
                    title = rd.short_title()
                except Exception:
                    pass
        except Exception:
            for tag in soup_full(_NOISE_TAGS):
                tag.decompose()
            body_html = str(soup_full.body or soup_full)

        soup = BeautifulSoup(body_html, "html.parser")
        for tag in soup(_NOISE_TAGS):
            tag.decompose()

        blocks: list[Block] = []
        text_parts: list[str] = []
        for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
            txt = el.get_text(" ", strip=True)
            if not txt:
                continue
            tag = el.name.lower()
            if tag.startswith("h"):
                try:
                    level = int(tag[1])
                except ValueError:
                    level = 1
                blocks.append(HeadingBlock(text=txt, level=level))
            else:
                blocks.append(ParagraphBlock(text=txt))
            text_parts.append(txt)

        return ExtractedDocument(
            text="\n".join(text_parts),
            blocks=blocks,
            meta={**meta, "title": title},
        )


__all__ = ["HtmlExtractor"]
