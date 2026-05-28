"""MIME-dispatch registry for extractors.

The registry is intentionally process-local. Production wiring calls
:func:`register_builtins` once at startup; tests can build a private
:class:`ExtractorRegistry` to avoid global state.

Resolution order:

1. Exact MIME match against an extractor's ``mime_types``.
2. Wildcard MIME match (``text/*``, ``application/*``).
3. ``NoExtractor`` raised.
"""
from __future__ import annotations

import logging
from typing import Any

from ai_portal.rag.extractors.protocol import (
    Extractor,
    NoExtractor,
)

logger = logging.getLogger(__name__)


class ExtractorRegistry:
    """In-memory map from MIME type to :class:`Extractor`."""

    def __init__(self) -> None:
        self._by_name: dict[str, Extractor] = {}
        self._by_mime: dict[str, Extractor] = {}
        self._wildcard: list[tuple[str, Extractor]] = []

    def register(self, extractor: Extractor) -> None:
        """Register an extractor. Raises on duplicate name or MIME."""
        if not getattr(extractor, "name", None):
            raise ValueError("extractor must define .name")
        if not getattr(extractor, "mime_types", None):
            raise ValueError(
                f"extractor {extractor.name!r} must define .mime_types"
            )
        if extractor.name in self._by_name:
            raise ValueError(f"extractor name already registered: {extractor.name!r}")
        self._by_name[extractor.name] = extractor
        for mime in extractor.mime_types:
            if mime.endswith("/*"):
                self._wildcard.append((mime[:-1], extractor))  # keep "text/"
                continue
            if mime in self._by_mime:
                raise ValueError(
                    f"mime {mime!r} already bound to "
                    f"{self._by_mime[mime].name!r}"
                )
            self._by_mime[mime] = extractor

    def resolve(self, mime: str) -> Extractor:
        """Return the extractor for ``mime`` or raise :class:`NoExtractor`."""
        mime = (mime or "").split(";", 1)[0].strip().lower()
        if not mime:
            raise NoExtractor("empty mime type")
        exact = self._by_mime.get(mime)
        if exact is not None:
            return exact
        for prefix, ext in self._wildcard:
            if mime.startswith(prefix):
                return ext
        raise NoExtractor(f"no extractor registered for mime {mime!r}")

    def get(self, name: str) -> Extractor | None:
        """Return the extractor with ``name`` or ``None``."""
        return self._by_name.get(name)

    def names(self) -> list[str]:
        """All registered extractor names (sorted)."""
        return sorted(self._by_name)

    async def extract(
        self, data: bytes, *, mime: str, meta: dict[str, Any] | None = None
    ):
        """Dispatch ``data`` to the right extractor by ``mime``."""
        ext = self.resolve(mime)
        return await ext.extract(data, meta or {})


_default = ExtractorRegistry()


def default_registry() -> ExtractorRegistry:
    """Return the process-wide registry instance."""
    return _default


def register_builtins(registry: ExtractorRegistry | None = None) -> ExtractorRegistry:
    """Register all bundled extractors. Idempotent per-registry.

    Heavy SDK imports stay lazy: this only imports the lightweight
    extractor *classes*, which themselves defer their SDK loads to
    :meth:`extract`.
    """
    reg = registry or _default
    # Local imports — avoid pulling every optional dep at startup.
    from ai_portal.rag.extractors.audio_transcribe import AudioTranscribeExtractor
    from ai_portal.rag.extractors.code import CodeExtractor
    from ai_portal.rag.extractors.docx import DocxExtractor
    from ai_portal.rag.extractors.email_eml import EmailExtractor
    from ai_portal.rag.extractors.html import HtmlExtractor
    from ai_portal.rag.extractors.image_ocr import ImageOcrExtractor
    from ai_portal.rag.extractors.markdown import MarkdownExtractor
    from ai_portal.rag.extractors.pdf import PdfExtractor
    from ai_portal.rag.extractors.plain import PlainTextExtractor
    from ai_portal.rag.extractors.pptx import PptxExtractor
    from ai_portal.rag.extractors.xlsx import XlsxExtractor

    candidates: list[Extractor] = [
        PdfExtractor(),
        DocxExtractor(),
        XlsxExtractor(),
        PptxExtractor(),
        HtmlExtractor(),
        MarkdownExtractor(),
        EmailExtractor(),
        ImageOcrExtractor(),
        AudioTranscribeExtractor(),
        CodeExtractor(),
        PlainTextExtractor(),
    ]
    for c in candidates:
        if c.name in reg._by_name:  # already registered — idempotent
            continue
        try:
            reg.register(c)
        except ValueError as exc:
            logger.warning("extractor_register_skip", extra={"name": c.name, "err": str(exc)})
    return reg


__all__ = ["ExtractorRegistry", "default_registry", "register_builtins"]
