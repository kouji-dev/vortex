"""Image OCR extractor.

Default backend: :mod:`pytesseract` (requires the Tesseract binary on the
host). When Tesseract is unavailable the extractor returns an empty
document with an ``ocr_skipped`` flag in ``meta`` rather than raising —
pipeline upstream decides how to handle it.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from ai_portal.rag.extractors.protocol import (
    ExtractedDocument,
    ImageCaptionBlock,
)


class ImageOcrExtractor:
    name = "image_ocr"
    mime_types = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
        "image/tiff",
        "image/bmp",
    }

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    async def extract(self, data: bytes, meta: dict[str, Any]) -> ExtractedDocument:
        try:
            from PIL import Image  # type: ignore
            import pytesseract  # type: ignore
        except Exception as exc:
            return ExtractedDocument(
                text="",
                blocks=[],
                meta={**meta, "ocr_skipped": True, "ocr_error": str(exc)},
            )
        try:
            img = Image.open(BytesIO(data))
            text = pytesseract.image_to_string(img) or ""
        except Exception as exc:
            return ExtractedDocument(
                text="",
                blocks=[],
                meta={**meta, "ocr_skipped": True, "ocr_error": str(exc)},
            )
        text = text.strip()
        blocks = (
            [ImageCaptionBlock(text=text, image_ref=meta.get("source_uri"))]
            if text
            else []
        )
        return ExtractedDocument(
            text=text,
            blocks=blocks,
            meta={**meta, "ocr_engine": "tesseract"},
        )


__all__ = ["ImageOcrExtractor"]
