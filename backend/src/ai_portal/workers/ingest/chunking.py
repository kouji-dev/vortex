"""Semantic chunker — splits text respecting document structure.

Returns list of (content, meta) tuples. Target ~500 tokens per chunk
(approximated as 2000 chars). Overlap is ~12% of chunk size.
"""
from __future__ import annotations

import re
from typing import TypedDict

TARGET_CHARS = 2000
OVERLAP_CHARS = 250  # ~12%


class ChunkMeta(TypedDict):
    source: str
    file_type: str
    section: str
    page: int | None
    char_start: int
    char_end: int


def semantic_chunks(
    text: str,
    *,
    file_type: str,
    filename: str,
    page: int | None = None,
) -> list[tuple[str, ChunkMeta]]:
    """Split text into overlapping semantic chunks."""
    text = text.strip()
    if not text:
        return []

    if file_type == "markdown":
        return _chunk_markdown(text, filename=filename)
    if file_type == "code":
        return _chunk_code(text, filename=filename)
    return _chunk_prose(text, filename=filename, file_type=file_type, page=page)


def _chunk_prose(
    text: str,
    *,
    filename: str,
    file_type: str,
    page: int | None,
) -> list[tuple[str, ChunkMeta]]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks: list[tuple[str, ChunkMeta]] = []
    current: list[str] = []
    current_chars = 0
    char_offset = 0

    def _flush(overlap_sentences: list[str]) -> None:
        nonlocal char_offset
        content = " ".join(current)
        start = char_offset
        end = start + len(content)
        section = current[0][:60] if current else ""
        chunks.append((
            content,
            ChunkMeta(
                source=filename,
                file_type=file_type,
                section=section,
                page=page,
                char_start=start,
                char_end=end,
            ),
        ))
        overlap_text = " ".join(overlap_sentences)
        char_offset = end - len(overlap_text)

    for sent in sentences:
        current.append(sent)
        current_chars += len(sent) + 1
        if current_chars >= TARGET_CHARS:
            overlap: list[str] = []
            overlap_size = 0
            for s in reversed(current):
                if overlap_size + len(s) > OVERLAP_CHARS:
                    break
                overlap.insert(0, s)
                overlap_size += len(s) + 1
            _flush(overlap)
            current = list(overlap)
            current_chars = sum(len(s) + 1 for s in current)

    if current:
        _flush([])

    return chunks


def _chunk_markdown(text: str, *, filename: str) -> list[tuple[str, ChunkMeta]]:
    heading_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))

    if not matches:
        return _chunk_prose(text, filename=filename, file_type="markdown", page=None)

    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append((heading, body))

    first_start = matches[0].start()
    if first_start > 0:
        preamble = text[:first_start].strip()
        if preamble:
            sections.insert(0, ("", preamble))

    chunks: list[tuple[str, ChunkMeta]] = []
    char_offset = 0
    prev_heading = ""

    for heading, body in sections:
        content = (f"{prev_heading}\n\n" if prev_heading else "") + (
            f"## {heading}\n\n" if heading else ""
        ) + body
        content = content.strip()
        if not content:
            prev_heading = heading
            continue

        if len(content) > TARGET_CHARS * 2:
            sub = _chunk_prose(content, filename=filename, file_type="markdown", page=None)
            for sub_content, sub_meta in sub:
                sub_meta["section"] = heading or sub_meta["section"]
            chunks.extend(sub)
        else:
            chunks.append((
                content,
                ChunkMeta(
                    source=filename,
                    file_type="markdown",
                    section=heading,
                    page=None,
                    char_start=char_offset,
                    char_end=char_offset + len(content),
                ),
            ))

        char_offset += len(content)
        prev_heading = heading

    return chunks


_CODE_SPLIT_PATTERN = re.compile(
    r"^(class\s+\w+|def\s+\w+|function\s+\w+|const\s+\w+\s*=\s*(?:async\s+)?(?:function|\())",
    re.MULTILINE,
)


def _chunk_code(text: str, *, filename: str) -> list[tuple[str, ChunkMeta]]:
    matches = list(_CODE_SPLIT_PATTERN.finditer(text))

    if not matches:
        return _chunk_prose(text, filename=filename, file_type="code", page=None)

    chunks: list[tuple[str, ChunkMeta]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if not content:
            continue
        section = match.group(0).strip()[:80]

        if len(content) > TARGET_CHARS * 3:
            sub = _chunk_prose(content, filename=filename, file_type="code", page=None)
            for sc, sm in sub:
                sm["section"] = section
            chunks.extend(sub)
        else:
            chunks.append((
                content,
                ChunkMeta(
                    source=filename,
                    file_type="code",
                    section=section,
                    page=None,
                    char_start=start,
                    char_end=end,
                ),
            ))

    if matches and matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            chunks.insert(0, (
                preamble,
                ChunkMeta(
                    source=filename,
                    file_type="code",
                    section="",
                    page=None,
                    char_start=0,
                    char_end=matches[0].start(),
                ),
            ))

    return chunks


def file_type_for_suffix(suffix: str) -> str:
    """Map file extension to chunker file_type."""
    suffix = suffix.lower().lstrip(".")
    if suffix == "pdf":
        return "pdf"
    if suffix in {"md", "markdown"}:
        return "markdown"
    if suffix in {"html", "htm"}:
        return "html"
    if suffix in {"py", "ts", "tsx", "js", "jsx", "go", "rs", "java",
                  "c", "cpp", "cs", "rb", "sh"}:
        return "code"
    return "prose"
