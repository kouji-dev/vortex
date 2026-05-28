"""Extractors subpackage.

Each extractor turns raw bytes (+ optional source meta) into an
``ExtractedDocument``. Concrete extractors are dispatched by MIME type
via the :mod:`registry`.
"""
from __future__ import annotations

from ai_portal.rag.extractors.protocol import (
    Block,
    CodeBlock,
    ExtractedDocument,
    Extractor,
    HeadingBlock,
    ImageCaptionBlock,
    NoExtractor,
    ParagraphBlock,
    TableBlock,
)
from ai_portal.rag.extractors.registry import (
    ExtractorRegistry,
    default_registry,
    register_builtins,
)

__all__ = [
    "Block",
    "CodeBlock",
    "ExtractedDocument",
    "Extractor",
    "ExtractorRegistry",
    "HeadingBlock",
    "ImageCaptionBlock",
    "NoExtractor",
    "ParagraphBlock",
    "TableBlock",
    "default_registry",
    "register_builtins",
]
