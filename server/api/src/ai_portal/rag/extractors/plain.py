"""Plain-text / fallback extractor for ``text/*`` MIME types."""
from __future__ import annotations

from typing import Any

from ai_portal.rag.extractors.protocol import (
    ExtractedDocument,
    ParagraphBlock,
)


class PlainTextExtractor:
    name = "plain"
    mime_types = {"text/plain", "text/*"}

    def supports(self, mime: str) -> bool:
        if mime in {"text/plain"}:
            return True
        return mime.startswith("text/")

    async def extract(self, data: bytes, meta: dict[str, Any]) -> ExtractedDocument:
        text = self._decode(data)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        blocks = [ParagraphBlock(text=p) for p in paragraphs]
        if not blocks and text.strip():
            blocks = [ParagraphBlock(text=text.strip())]
        return ExtractedDocument(text=text, blocks=blocks, meta={**meta})

    @staticmethod
    def _decode(data: bytes) -> str:
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")


__all__ = ["PlainTextExtractor"]
