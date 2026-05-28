"""Stage 3 — normalize.

- Re-encode text to NFC + UTF-8 clean.
- Strip control chars (except ``\\n`` and ``\\t``).
- Detect language (lazy via ``langdetect``) when not already set.
- Recompute content hash for downstream dedupe in Stage 8.
"""
from __future__ import annotations

import hashlib
import unicodedata

from ai_portal.rag.pipeline.runner import Stage, StageCtx, StageError

_CONTROL_KEEP = {"\n", "\t"}


def _strip_controls(text: str) -> str:
    return "".join(
        ch for ch in text if ch in _CONTROL_KEEP or unicodedata.category(ch)[0] != "C"
    )


async def normalize_stage(ctx: StageCtx) -> StageCtx:
    if ctx.extracted is None:
        raise StageError(Stage.normalize, "no extracted document")
    doc = ctx.extracted
    text = unicodedata.normalize("NFC", doc.text or "")
    text = _strip_controls(text)
    doc.text = text
    # Language detection — best-effort, skipped on import error.
    if not doc.meta.get("language"):
        try:
            from langdetect import detect  # type: ignore

            sample = text[:2000]
            if sample.strip():
                doc.meta["language"] = detect(sample)
        except Exception:
            pass
    # Content hash for dedupe.
    doc.meta["content_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ctx


__all__ = ["normalize_stage"]
