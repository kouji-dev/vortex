"""Email extractor.

Handles RFC-822 ``.eml`` via stdlib :mod:`email.parser`. The ``.msg``
format (Outlook) is loaded lazily through ``extract-msg`` when present.
"""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
from typing import Any

from ai_portal.rag.extractors.protocol import (
    Block,
    ExtractedDocument,
    ParagraphBlock,
)


class EmailExtractor:
    name = "email_eml"
    mime_types = {"message/rfc822", "application/vnd.ms-outlook"}

    def supports(self, mime: str) -> bool:
        return mime in self.mime_types

    async def extract(self, data: bytes, meta: dict[str, Any]) -> ExtractedDocument:
        # .msg path
        if meta.get("source_uri", "").lower().endswith(".msg"):
            try:
                import extract_msg  # type: ignore

                msg = extract_msg.Message(data)
                return ExtractedDocument(
                    text=msg.body or "",
                    blocks=[ParagraphBlock(text=msg.body or "")],
                    meta={
                        **meta,
                        "subject": msg.subject,
                        "from": msg.sender,
                        "to": msg.to,
                        "date": str(msg.date) if msg.date else None,
                    },
                )
            except Exception:
                # Fall through to .eml parser as a best-effort.
                pass

        msg = BytesParser(policy=policy.default).parsebytes(data)
        body_text = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    body_text = part.get_content() or ""
                    break
                if not body_text and ctype == "text/html":
                    body_text = part.get_content() or ""
        else:
            try:
                body_text = msg.get_content() or ""
            except Exception:
                body_text = msg.get_payload(decode=False) or ""

        blocks: list[Block] = []
        for line in body_text.splitlines():
            s = line.strip()
            if s:
                blocks.append(ParagraphBlock(text=s))

        return ExtractedDocument(
            text=body_text,
            blocks=blocks,
            meta={
                **meta,
                "subject": msg.get("Subject"),
                "from": msg.get("From"),
                "to": msg.get("To"),
                "date": msg.get("Date"),
            },
        )


__all__ = ["EmailExtractor"]
