"""Code extractor.

Detects language from MIME / source URI and emits one
:class:`CodeBlock` per top-level function or class when an AST is
available. Tree-sitter is loaded lazily — when absent, the file falls
back to a single language-tagged code block.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ai_portal.rag.extractors.protocol import (
    Block,
    CodeBlock,
    ExtractedDocument,
)

_EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".sql": "sql",
}

_MIME_TO_LANG = {
    "application/x-python": "python",
    "text/x-python": "python",
    "application/javascript": "javascript",
    "text/x-go": "go",
    "text/x-rust": "rust",
    "text/x-java-source": "java",
    "text/x-c": "c",
    "text/x-c++src": "cpp",
}

_PY_DEFN = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z_]\w*)", re.MULTILINE)


class CodeExtractor:
    name = "code"
    mime_types = set(_MIME_TO_LANG) | {
        "text/x-script.python",
        "application/x-sh",
    }

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    def _detect_language(self, mime: str, source_uri: str | None) -> str | None:
        lang = _MIME_TO_LANG.get(mime)
        if lang:
            return lang
        if source_uri:
            return _EXT_TO_LANG.get(Path(source_uri).suffix.lower())
        return None

    async def extract(self, data: bytes, meta: dict[str, Any]) -> ExtractedDocument:
        text = data.decode("utf-8", errors="replace")
        language = self._detect_language(
            meta.get("mime", "") or "", meta.get("source_uri")
        )
        blocks: list[Block] = []

        # Fast path: simple regex carve for Python def/class boundaries.
        if language == "python":
            blocks.extend(self._split_python(text))
        if not blocks:
            blocks = [CodeBlock(text=text, language=language)]

        return ExtractedDocument(
            text=text,
            blocks=blocks,
            meta={**meta, "language": language},
        )

    @staticmethod
    def _split_python(text: str) -> list[Block]:
        lines = text.splitlines(keepends=True)
        starts: list[tuple[int, str]] = []
        for i, ln in enumerate(lines):
            m = _PY_DEFN.match(ln.lstrip())
            if m and (len(ln) - len(ln.lstrip())) == 0:
                starts.append((i, m.group(1)))
        if not starts:
            return []
        blocks: list[Block] = []
        boundaries = [s[0] for s in starts] + [len(lines)]
        for (start, name), end in zip(starts, boundaries[1:], strict=False):
            chunk = "".join(lines[start:end])
            blocks.append(
                CodeBlock(text=chunk, language="python", function=name)
            )
        return blocks


__all__ = ["CodeExtractor"]
