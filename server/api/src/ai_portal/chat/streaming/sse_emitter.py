from __future__ import annotations
from ai_portal.chat.sse import SseEvent


def encode(event: SseEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"
