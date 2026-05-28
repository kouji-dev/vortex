"""PDF extractor.

Uses :mod:`pypdf` as the always-available fast path. When ``unstructured``
is installed it is invoked lazily to recover table blocks; failures fall
back silently to the pypdf-only path.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from ai_portal.rag.extractors.protocol import (
    Block,
    ExtractedDocument,
    HeadingBlock,
    ParagraphBlock,
    TableBlock,
)


class PdfExtractor:
    """Extract text + headings + (best-effort) tables from a PDF."""

    name = "pdf"
    mime_types = {"application/pdf"}

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    async def extract(self, data: bytes, meta: dict[str, Any]) -> ExtractedDocument:
        from pypdf import PdfReader  # always available

        reader = PdfReader(BytesIO(data))
        blocks: list[Block] = []
        text_parts: list[str] = []
        for page_no, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            for line in page_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if self._looks_like_heading(line):
                    blocks.append(HeadingBlock(text=line, level=1, page=page_no))
                else:
                    blocks.append(ParagraphBlock(text=line, page=page_no))
            text_parts.append(page_text)

        # Optional table recovery via unstructured — lazy + best-effort.
        try:
            from unstructured.partition.pdf import partition_pdf  # type: ignore

            for el in partition_pdf(file=BytesIO(data), strategy="fast"):
                if getattr(el, "category", "") == "Table":
                    rows = self._parse_html_table(
                        getattr(getattr(el, "metadata", None), "text_as_html", None)
                    )
                    if rows:
                        blocks.append(TableBlock(rows=rows))
        except Exception:
            pass

        title: str | None = None
        try:
            md = reader.metadata
            if md is not None:
                t = md.get("/Title")
                if t:
                    title = str(t)
        except Exception:
            pass

        return ExtractedDocument(
            text="\n".join(text_parts),
            blocks=blocks,
            meta={
                **meta,
                "page_count": len(reader.pages),
                "title": title,
            },
        )

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        return len(line) < 80 and (line.isupper() or line.endswith(":"))

    @staticmethod
    def _parse_html_table(html: str | None) -> list[list[str]]:
        if not html:
            return []
        try:
            from bs4 import BeautifulSoup  # type: ignore
        except Exception:
            return []
        soup = BeautifulSoup(html, "html.parser")
        return [
            [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            for row in soup.find_all("tr")
        ]


__all__ = ["PdfExtractor"]
