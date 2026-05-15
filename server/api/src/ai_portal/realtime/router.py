"""Global per-user SSE endpoint.

Frontend opens one ``EventSource("/api/events")`` after login and receives a
fan-out of server-pushed updates that aren't tied to a single REST request
(e.g. conversation title generation completing in the background after a
chat message stream).

Wire format follows the standard SSE spec — one ``event:`` + one ``data:``
line per message, blank line terminates the event.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ai_portal.auth.deps import get_current_user
from ai_portal.auth.model import User
from ai_portal.core.realtime import subscribe_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["realtime"])

# Send a comment line every N seconds so reverse proxies / load balancers
# don't kill the idle TCP connection. Browsers ignore SSE comments.
_HEARTBEAT_INTERVAL_SECONDS = 25


def _encode_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/events")
async def events(
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    user_id = user.id

    async def _gen() -> AsyncIterator[str]:
        # Hello frame so the client knows the connection is live.
        yield _encode_sse("ready", {"user_id": user_id})

        sub = subscribe_user(user_id).__aiter__()
        next_task: asyncio.Task[dict[str, Any]] | None = None
        try:
            while True:
                if await request.is_disconnected():
                    return
                if next_task is None:
                    next_task = asyncio.create_task(sub.__anext__())
                try:
                    payload = await asyncio.wait_for(
                        asyncio.shield(next_task),
                        timeout=_HEARTBEAT_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    # Heartbeat — keep the connection warm.
                    yield ": keepalive\n\n"
                    continue
                except StopAsyncIteration:
                    return
                next_task = None
                event = payload.get("event")
                data = payload.get("data") or {}
                if not isinstance(event, str) or not event:
                    continue
                yield _encode_sse(event, data)
        finally:
            if next_task is not None and not next_task.done():
                next_task.cancel()
            try:
                await sub.aclose()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # nginx: disable proxy buffering
            "Connection": "keep-alive",
        },
    )
