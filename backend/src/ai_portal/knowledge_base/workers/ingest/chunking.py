"""Document chunking via Chonkie — semantic, code, and prose strategies.

Returns list of (content, meta) tuples. Uses Chonkie's SemanticChunker for
prose/markdown (embedding-based boundary detection) and CodeChunker for
source code (tree-sitter AST). Falls back to RecursiveChunker when the
semantic model isn't needed.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import TypedDict

from chonkie import CodeChunker, RecursiveChunker, SemanticChunker

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
SEMANTIC_SIMILARITY_THRESHOLD = 0.5


class ChunkMeta(TypedDict):
    source: str
    file_type: str
    section: str
    page: int | None
    char_start: int
    char_end: int


@lru_cache(maxsize=1)
def _get_semantic_chunker() -> SemanticChunker:
    return SemanticChunker(
        embedding_model="minishlab/potion-base-32M",
        chunk_size=CHUNK_SIZE,
        threshold=SEMANTIC_SIMILARITY_THRESHOLD,
    )


@lru_cache(maxsize=1)
def _get_recursive_chunker() -> RecursiveChunker:
    return RecursiveChunker(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=64,
    )


@lru_cache(maxsize=1)
def _get_code_chunker() -> CodeChunker:
    return CodeChunker(
        language="auto",
        chunk_size=CHUNK_SIZE * 4,
    )


def _section_label(text: str) -> str:
    """Extract a short section label from chunk text."""
    first_line = text.split("\n", 1)[0].strip()
    if first_line.startswith("#"):
        return first_line.lstrip("# ").strip()[:80]
    return first_line[:60]


def semantic_chunks(
    text: str,
    file_type: str,
    filename: str,
    page: int,
) -> list[tuple[str, ChunkMeta]]:
    """Split text into chunks using Chonkie. Public API matches the old module."""
    text = text.strip()
    if not text:
        return []

    if file_type == "code":
        return _chunk_code(text, filename=filename, page=page)
    if file_type in {"markdown", "prose", "pdf"}:
        return _chunk_semantic(text, filename=filename, file_type=file_type, page=page)
    return _chunk_fallback(text, filename=filename, file_type=file_type, page=page)


def _chunk_semantic(
    text: str,
    *,
    filename: str,
    file_type: str,
    page: int,
) -> list[tuple[str, ChunkMeta]]:
    try:
        chunker = _get_semantic_chunker()
        raw_chunks = chunker.chunk(text)
    except Exception:
        logger.warning("semantic_chunker_failed_falling_back", exc_info=True)
        return _chunk_fallback(text, filename=filename, file_type=file_type, page=page)

    results: list[tuple[str, ChunkMeta]] = []
    for ch in raw_chunks:
        content = ch.text.strip()
        if not content:
            continue
        results.append((
            content,
            ChunkMeta(
                source=filename,
                file_type=file_type,
                section=_section_label(content),
                page=page,
                char_start=ch.start_index,
                char_end=ch.end_index,
            ),
        ))
    return results


def _chunk_code(
    text: str,
    *,
    filename: str,
    page: int,
) -> list[tuple[str, ChunkMeta]]:
    try:
        chunker = _get_code_chunker()
        raw_chunks = chunker.chunk(text)
    except Exception:
        logger.warning("code_chunker_failed_falling_back", exc_info=True)
        return _chunk_fallback(text, filename=filename, file_type="code", page=page)

    results: list[tuple[str, ChunkMeta]] = []
    for ch in raw_chunks:
        content = ch.text.strip()
        if not content:
            continue
        results.append((
            content,
            ChunkMeta(
                source=filename,
                file_type="code",
                section=_section_label(content),
                page=page,
                char_start=ch.start_index,
                char_end=ch.end_index,
            ),
        ))
    return results


def _chunk_fallback(
    text: str,
    *,
    filename: str,
    file_type: str,
    page: int,
) -> list[tuple[str, ChunkMeta]]:
    chunker = _get_recursive_chunker()
    raw_chunks = chunker.chunk(text)

    results: list[tuple[str, ChunkMeta]] = []
    for ch in raw_chunks:
        content = ch.text.strip()
        if not content:
            continue
        results.append((
            content,
            ChunkMeta(
                source=filename,
                file_type=file_type,
                section=_section_label(content),
                page=page,
                char_start=ch.start_index,
                char_end=ch.end_index,
            ),
        ))
    return results


def file_type_for_suffix(suffix: str) -> str:
    """Map file extension to chunker file_type."""
    suffix = suffix.lower().lstrip(".")
    if suffix == "pdf":
        return "pdf"
    if suffix in {"md", "markdown"}:
        return "markdown"
    if suffix in {"html", "htm"}:
        return "prose"
    if suffix in {
        "py", "ts", "tsx", "js", "jsx", "go", "rs", "java",
        "c", "cpp", "cs", "rb", "sh",
    }:
        return "code"
    return "prose"
