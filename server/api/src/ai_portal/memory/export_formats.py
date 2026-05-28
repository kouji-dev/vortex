"""Memory export serializers — json / jsonl / csv / markdown.

Input is the dict returned by ``MemoryService.export_for_user`` (shape:
``{"memories": [...]}``). All serializers return bytes so the caller can
hand them to BlobStore or a FastAPI ``Response`` directly.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Iterable

SUPPORTED = ("json", "jsonl", "csv", "md")

# Column order for CSV / readability
_COLS = (
    "id",
    "type",
    "scope_kind",
    "scope_ids",
    "text",
    "importance",
    "confidence",
    "pinned",
    "tags",
    "source_conversation_id",
    "extractor_model",
    "created_at",
    "last_used_at",
    "expires_at",
    "deleted_at",
)


def content_type(fmt: str) -> str:
    return {
        "json": "application/json",
        "jsonl": "application/x-ndjson",
        "csv": "text/csv",
        "md": "text/markdown",
    }[fmt]


def file_ext(fmt: str) -> str:
    return {"json": "json", "jsonl": "jsonl", "csv": "csv", "md": "md"}[fmt]


def _memories(payload: dict) -> Iterable[dict]:
    return payload.get("memories", []) or []


def to_json(payload: dict) -> bytes:
    return json.dumps(payload, default=str).encode("utf-8")


def to_jsonl(payload: dict) -> bytes:
    buf = io.StringIO()
    for m in _memories(payload):
        buf.write(json.dumps(m, default=str))
        buf.write("\n")
    return buf.getvalue().encode("utf-8")


def _csv_value(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str)
    return str(v)


def to_csv(payload: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_COLS)
    for m in _memories(payload):
        writer.writerow([_csv_value(m.get(c)) for c in _COLS])
    return buf.getvalue().encode("utf-8")


def to_markdown(payload: dict) -> bytes:
    lines: list[str] = ["# Memory Export", ""]
    by_type: dict[str, list[dict]] = {}
    for m in _memories(payload):
        by_type.setdefault(m.get("type") or "unknown", []).append(m)
    if not by_type:
        lines.append("_No memories._")
        return "\n".join(lines).encode("utf-8")
    for t in sorted(by_type):
        rows = by_type[t]
        lines.append(f"## {t} ({len(rows)})")
        lines.append("")
        for m in rows:
            text = (m.get("text") or "").replace("\n", " ").strip()
            tags = m.get("tags") or []
            tag_str = f"  _tags: {', '.join(tags)}_" if tags else ""
            pinned = " **[pinned]**" if m.get("pinned") else ""
            lines.append(f"- {text}{pinned}{tag_str}")
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def render(fmt: str, payload: dict) -> bytes:
    fmt = (fmt or "json").lower()
    if fmt not in SUPPORTED:
        raise ValueError(f"unsupported format: {fmt}")
    return {"json": to_json, "jsonl": to_jsonl, "csv": to_csv, "md": to_markdown}[fmt](
        payload
    )


__all__ = [
    "SUPPORTED",
    "content_type",
    "file_ext",
    "render",
    "to_csv",
    "to_json",
    "to_jsonl",
    "to_markdown",
]
