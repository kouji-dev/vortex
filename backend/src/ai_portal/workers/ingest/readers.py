"""Streaming file readers — yield text pages/sections without loading whole file."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator


def stream_text_pages(path: Path) -> Iterator[str]:
    """Yield text segments from a file without loading it all into memory.

    Supported types: .txt, .md, .py, .ts, .js, .html, .pdf
    Raises ValueError("unsupported_type:<suffix>") for unknown types.
    """
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md", ".py", ".ts", ".js", ".tsx", ".jsx", ".go",
                  ".rs", ".java", ".c", ".cpp", ".cs", ".rb", ".sh"}:
        yield from _stream_text_file(path)
    elif suffix == ".html":
        yield from _stream_html_file(path)
    elif suffix == ".pdf":
        yield from _stream_pdf_file(path)
    else:
        raise ValueError(f"unsupported_type:{suffix}")


def _stream_text_file(path: Path) -> Iterator[str]:
    """Yield the file in 4 KB line-buffered chunks."""
    buffer: list[str] = []
    buffer_chars = 0
    target = 4096

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            buffer.append(line)
            buffer_chars += len(line)
            if buffer_chars >= target:
                yield "".join(buffer)
                buffer = []
                buffer_chars = 0
    if buffer:
        yield "".join(buffer)


def _stream_html_file(path: Path) -> Iterator[str]:
    """Strip HTML tags and yield as plain text."""
    try:
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.parts: list[str] = []

            def handle_data(self, data: str) -> None:
                stripped = data.strip()
                if stripped:
                    self.parts.append(stripped)

        parser = _TextExtractor()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        text = "\n".join(parser.parts)
        if text:
            yield text
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"html_read_failed:{exc}") from exc


def _stream_pdf_file(path: Path) -> Iterator[str]:
    """Yield one page of text at a time from a PDF."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                yield text
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"pdf_read_failed:{exc}") from exc
