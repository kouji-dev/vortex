"""error_handler — convert provider exceptions to SSE error + done events."""

from __future__ import annotations

import logging
import uuid

from ai_portal.chat.item_kinds import ItemKind, ItemStatus
from ai_portal.chat.items import ErrorPayload
from ai_portal.chat.sse import SseDoneEvent, SseErrorEvent, SseEvent
from ai_portal.chat.streaming.item_writer import ItemWriter

logger = logging.getLogger(__name__)


def _friendly_message(exc: Exception) -> str:
    """Convert a provider exception into a human-readable error string."""
    msg = str(exc)
    exc_type = type(exc).__name__

    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        import re
        m = re.search(r"retry.*?(\d+(?:\.\d+)?s)", msg, re.IGNORECASE)
        hint = f" Retry in {m.group(1)}." if m else ""
        return f"Rate limit exceeded for this model.{hint} Try a different model or wait before retrying."

    if "401" in msg or "403" in msg or "UNAUTHENTICATED" in msg or "API_KEY" in msg.upper():
        return "Invalid or missing API key. Check your API key configuration."

    if "404" in msg or "NOT_FOUND" in msg or ("model" in msg.lower() and "not found" in msg.lower()):
        return f"Model not found or unavailable. ({exc_type})"

    if any(k in exc_type.lower() for k in ("timeout", "connection", "network")):
        return "Could not reach the AI provider (network error). Please try again."

    if "context" in msg.lower() or ("token" in msg.lower() and "limit" in msg.lower()):
        return "Message is too long for this model. Try shortening your message."

    short = msg[:200]
    return f"Model error ({exc_type}): {short}"


async def handle_stream_error(
    *,
    exc: Exception,
    writer: ItemWriter,
    turn_id: uuid.UUID,
) -> list[SseEvent]:
    """Persist an error item and return error + done SSE events.

    Returns a list (not a generator) so callers can emit them in order.
    """
    logger.exception("stream_error turn_id=%s exc_type=%s", turn_id, type(exc).__name__)

    code = type(exc).__name__
    message = _friendly_message(exc)

    try:
        await writer.insert_error(turn_id=turn_id, code=code, message=message)
        await writer.insert_turn_end(turn_id=turn_id, reason="error")
    except Exception:
        logger.exception("failed to write error item for turn_id=%s", turn_id)

    error_event = SseEvent.model_validate({
        "event_type": "error",
        "error": {"code": code, "message": message},
    })
    done_event = SseEvent.model_validate({"event_type": "done"})
    return [error_event, done_event]
