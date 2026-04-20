# tests/chat/streaming/test_error_handler.py
import uuid

import pytest

from ai_portal.chat.streaming.error_handler import handle_stream_error
from ai_portal.chat.streaming.item_writer import ItemWriter


async def test_handle_stream_error_emits_error_and_done(async_db_session, thread_fixture, org_fixture):
    writer = ItemWriter(session=async_db_session, thread_id=thread_fixture.id, org_id=org_fixture.id)
    turn_id = uuid.uuid4()

    events = await handle_stream_error(
        exc=ValueError("something went wrong"),
        writer=writer,
        turn_id=turn_id,
    )

    assert len(events) == 2
    # First event is error
    import json
    first = json.loads(events[0].model_dump_json())
    assert first["event_type"] == "error"
    assert "error" in first

    # Second event is done
    second = json.loads(events[1].model_dump_json())
    assert second["event_type"] == "done"


async def test_friendly_message_rate_limit():
    from ai_portal.chat.streaming.error_handler import _friendly_message
    msg = _friendly_message(Exception("429 Too Many Requests: RESOURCE_EXHAUSTED"))
    assert "Rate limit" in msg


async def test_friendly_message_auth_error():
    from ai_portal.chat.streaming.error_handler import _friendly_message
    msg = _friendly_message(Exception("401 UNAUTHENTICATED API_KEY invalid"))
    assert "API key" in msg
