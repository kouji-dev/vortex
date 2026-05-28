"""Audio transcription extractor.

Routes through the Gateway facade so provider selection (Whisper, Voyage,
self-hosted) and policy enforcement stay centralised. No SDK is imported
here directly.
"""
from __future__ import annotations

from typing import Any

from ai_portal.rag.extractors.protocol import (
    ExtractedDocument,
    ParagraphBlock,
)


class AudioTranscribeExtractor:
    name = "audio_transcribe"
    mime_types = {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/m4a",
        "audio/flac",
        "audio/ogg",
        "audio/webm",
    }

    #: Injected from main.py startup. Falls back to facade lookup.
    transcribe_fn = None  # type: ignore[assignment]

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    async def extract(self, data: bytes, meta: dict[str, Any]) -> ExtractedDocument:
        fn = self.transcribe_fn
        if fn is None:
            # Best-effort gateway lookup; emit empty doc when unavailable.
            try:
                from ai_portal.gateway import facade as _f

                facade = _f.get_default_facade()
                fn = getattr(facade, "transcribe", None)
            except Exception:
                fn = None
        if fn is None:
            return ExtractedDocument(
                text="",
                blocks=[],
                meta={**meta, "transcribe_skipped": True},
            )
        result = await fn(data=data, meta=meta)
        text = (result or {}).get("text", "") if isinstance(result, dict) else (result or "")
        segments = (result or {}).get("segments", []) if isinstance(result, dict) else []
        blocks = [ParagraphBlock(text=text)] if text else []
        return ExtractedDocument(
            text=text,
            blocks=blocks,
            meta={**meta, "segments": segments},
        )


__all__ = ["AudioTranscribeExtractor"]
