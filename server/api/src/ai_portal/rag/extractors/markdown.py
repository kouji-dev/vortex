"""Markdown / RST / AsciiDoc extractor.

Splits by ATX (``# H1``) and setext (``Title\\n====``) headings.
Fenced code blocks become :class:`CodeBlock` with the lexer hint.
"""
from __future__ import annotations

import re
from typing import Any

from ai_portal.rag.extractors.protocol import (
    Block,
    CodeBlock,
    ExtractedDocument,
    HeadingBlock,
    ParagraphBlock,
)

_ATX = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SETEXT_H1 = re.compile(r"^=+\s*$")
_SETEXT_H2 = re.compile(r"^-+\s*$")
_FENCE = re.compile(r"^\s*(```+|~~~+)\s*([\w+-]*)?\s*$")


class MarkdownExtractor:
    name = "markdown"
    mime_types = {
        "text/markdown",
        "text/x-markdown",
        "text/x-rst",
        "text/asciidoc",
        "text/x-asciidoc",
    }

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    async def extract(self, data: bytes, meta: dict[str, Any]) -> ExtractedDocument:
        raw = data.decode("utf-8", errors="replace")
        lines = raw.splitlines()
        blocks: list[Block] = []
        text_parts: list[str] = []
        i = 0
        para_buf: list[str] = []

        def flush_para() -> None:
            if para_buf:
                txt = " ".join(para_buf).strip()
                if txt:
                    blocks.append(ParagraphBlock(text=txt))
                    text_parts.append(txt)
                para_buf.clear()

        while i < len(lines):
            line = lines[i]
            m_fence = _FENCE.match(line)
            if m_fence:
                flush_para()
                lang = (m_fence.group(2) or "").lower() or None
                buf: list[str] = []
                i += 1
                while i < len(lines) and not _FENCE.match(lines[i]):
                    buf.append(lines[i])
                    i += 1
                code = "\n".join(buf)
                blocks.append(CodeBlock(text=code, language=lang))
                text_parts.append(code)
                i += 1
                continue

            m_atx = _ATX.match(line)
            if m_atx:
                flush_para()
                level = len(m_atx.group(1))
                txt = m_atx.group(2).strip()
                blocks.append(HeadingBlock(text=txt, level=level))
                text_parts.append(txt)
                i += 1
                continue

            # setext detection — current line is the title text, next is underline
            if i + 1 < len(lines) and line.strip():
                nxt = lines[i + 1]
                if _SETEXT_H1.match(nxt):
                    flush_para()
                    blocks.append(HeadingBlock(text=line.strip(), level=1))
                    text_parts.append(line.strip())
                    i += 2
                    continue
                if _SETEXT_H2.match(nxt):
                    flush_para()
                    blocks.append(HeadingBlock(text=line.strip(), level=2))
                    text_parts.append(line.strip())
                    i += 2
                    continue

            if not line.strip():
                flush_para()
            else:
                para_buf.append(line.strip())
            i += 1
        flush_para()

        return ExtractedDocument(
            text="\n".join(text_parts),
            blocks=blocks,
            meta={**meta},
        )


__all__ = ["MarkdownExtractor"]
