"""Extractor protocol + block types.

An :class:`Extractor` turns ``(data, meta)`` into an
:class:`ExtractedDocument` carrying both the flattened text and a list of
typed blocks (paragraph, heading, table, code, image caption). The 8-stage
ingestion pipeline consumes this shape in the *extract* stage.

The protocol is intentionally tiny — concrete extractors live under
``ai_portal.rag.extractors.<format>``. All heavy provider/SDK imports are
performed lazily inside :meth:`Extractor.extract` so a process that does
not exercise a given extractor never pays its import cost.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

BlockKind = Literal[
    "paragraph",
    "heading",
    "table",
    "code",
    "image_caption",
]


@dataclass(slots=True)
class ParagraphBlock:
    """Flowing prose paragraph."""

    text: str
    page: int | None = None
    kind: BlockKind = "paragraph"


@dataclass(slots=True)
class HeadingBlock:
    """Heading / section title. ``level`` is 1-based (H1 == 1)."""

    text: str
    level: int = 1
    page: int | None = None
    kind: BlockKind = "heading"


@dataclass(slots=True)
class TableBlock:
    """Tabular data. ``rows`` is row-major (first row often headers)."""

    rows: list[list[str]] = field(default_factory=list)
    page: int | None = None
    sheet: str | None = None
    kind: BlockKind = "table"


@dataclass(slots=True)
class CodeBlock:
    """Source-code segment. ``language`` is the lower-case identifier."""

    text: str
    language: str | None = None
    function: str | None = None
    kind: BlockKind = "code"


@dataclass(slots=True)
class ImageCaptionBlock:
    """Caption / OCR text bound to an image asset."""

    text: str
    image_ref: str | None = None
    page: int | None = None
    kind: BlockKind = "image_caption"


Block = (
    ParagraphBlock
    | HeadingBlock
    | TableBlock
    | CodeBlock
    | ImageCaptionBlock
)


@dataclass(slots=True)
class ExtractedDocument:
    """Result of running an :class:`Extractor` against raw bytes."""

    text: str
    blocks: list[Block] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class NoExtractor(LookupError):
    """Raised by the registry when no extractor matches a MIME type."""


@runtime_checkable
class Extractor(Protocol):
    """Pluggable extractor.

    Implementations MUST set:

    - :attr:`name` — short stable id (e.g. ``"pdf"``)
    - :attr:`mime_types` — set of MIME types they accept

    Heavy SDK imports should be deferred to :meth:`extract`.
    """

    name: str
    mime_types: set[str]

    def supports(self, mime: str) -> bool:  # pragma: no cover - protocol
        ...

    async def extract(
        self, data: bytes, meta: dict[str, Any]
    ) -> ExtractedDocument:  # pragma: no cover - protocol
        ...


__all__ = [
    "Block",
    "BlockKind",
    "CodeBlock",
    "ExtractedDocument",
    "Extractor",
    "HeadingBlock",
    "ImageCaptionBlock",
    "NoExtractor",
    "ParagraphBlock",
    "TableBlock",
]
