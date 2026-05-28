"""Citation tracking + marker injection.

A ``CitationTracker`` assigns stable 1-based indices to the hits used in an
answer. Markers like ``[1]``, ``[2]`` are inserted into the streamed answer
either by the LLM prompt or by post-processing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ai_portal.rag.search.types import SearchHit


@dataclass
class Citation:
    index: int  # 1-based marker shown in the answer
    chunk_id: str
    document_id: str
    kb_id: int
    title: str
    snippet: str
    permalink: str | None = None


@dataclass
class CitationTracker:
    """Maps chunk_id → 1-based citation index. Preserves insertion order."""

    _by_chunk: dict[str, Citation] = field(default_factory=dict)

    def register(self, hit: SearchHit) -> Citation:
        if hit.chunk_id in self._by_chunk:
            return self._by_chunk[hit.chunk_id]
        idx = len(self._by_chunk) + 1
        meta = hit.meta or {}
        title = str(meta.get("title") or meta.get("filename") or hit.document_id)
        permalink = meta.get("source_uri") or meta.get("url") or meta.get("permalink")
        snippet = (hit.text or "").strip()
        if len(snippet) > 240:
            snippet = snippet[:237].rstrip() + "…"
        c = Citation(
            index=idx,
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            kb_id=hit.kb_id,
            title=title,
            snippet=snippet,
            permalink=str(permalink) if permalink else None,
        )
        self._by_chunk[hit.chunk_id] = c
        return c

    def register_all(self, hits: list[SearchHit]) -> list[Citation]:
        return [self.register(h) for h in hits]

    def list(self) -> list[Citation]:
        return sorted(self._by_chunk.values(), key=lambda c: c.index)

    def __len__(self) -> int:
        return len(self._by_chunk)


_MARKER_RE = re.compile(r"\[(\d+)\]")


def used_marker_indices(text: str) -> list[int]:
    """Return all 1-based citation indices found in the text, in order."""
    return [int(m.group(1)) for m in _MARKER_RE.finditer(text)]


def inject_citation_markers(answer: str, *, fallback_indices: list[int] | None = None) -> str:
    """Ensure at least one citation marker is present.

    If the model already emitted ``[N]`` markers, leave the answer as-is.
    Otherwise, append the fallback set as ``[1] [2] …``.
    """
    if _MARKER_RE.search(answer or ""):
        return answer
    if not fallback_indices:
        return answer
    suffix = " ".join(f"[{i}]" for i in fallback_indices)
    sep = "" if answer.endswith(" ") or not answer else " "
    return f"{answer}{sep}{suffix}"
