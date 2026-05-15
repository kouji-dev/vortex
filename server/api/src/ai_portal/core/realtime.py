"""Redis pub/sub for fan-out of per-user real-time events.

Used by the global SSE endpoint (``/api/events``) and any code that wants to
push a server-originated update to a user's open browser tabs (e.g. the
post-stream title generator publishing ``conversation_title_changed``).

Channel layout:

    realtime:user:{user_id}    →  events scoped to a single user, all tabs

Payload on the wire is a JSON object: ``{"event": "<name>", "data": {...}}``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import redis.asyncio as aioredis

from ai_portal.core.config import get_settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None


def _channel_for(user_id: int) -> str:
    return f"realtime:user:{user_id}"


async def get_redis() -> aioredis.Redis:
    """Lazily build a singleton async Redis client. Raises if REDIS_URL is empty."""
    global _client
    if _client is None:
        url = get_settings().redis_url.strip()
        if not url:
            raise RuntimeError("REDIS_URL is not configured")
        _client = aioredis.from_url(url, decode_responses=True)
    return _client


async def publish_user_event(user_id: int, event: str, data: dict[str, Any]) -> None:
    """Fire-and-forget publish; logs and swallows transport errors so callers
    inside a streaming response never crash on a flaky redis."""
    try:
        r = await get_redis()
        payload = json.dumps({"event": event, "data": data})
        await r.publish(_channel_for(user_id), payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("realtime_publish_failed", extra={"event": event, "err": str(exc)})


async def subscribe_user(user_id: int) -> AsyncIterator[dict[str, Any]]:
    """Async iterator yielding decoded payloads ``{"event", "data"}`` for one user.

    Caller is responsible for managing the lifetime (cancel the task on client
    disconnect). The underlying pubsub is closed in the ``finally`` block.
    """
    r = await get_redis()
    pubsub = r.pubsub()
    channel = _channel_for(user_id)
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            raw = message.get("data")
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("realtime_bad_payload", extra={"raw": str(raw)[:120]})
                continue
    finally:
        try:
            await pubsub.unsubscribe(channel)
        finally:
            await pubsub.aclose()
