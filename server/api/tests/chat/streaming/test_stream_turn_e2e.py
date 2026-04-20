# tests/chat/streaming/test_stream_turn_e2e.py
import pytest

from ai_portal.chat.streaming.orchestrator import stream_turn


async def test_stream_turn_happy_path(async_db_session, thread_fixture, user_fixture, patched_fake_provider):
    """End-to-end streaming turn with a fake provider emitting text."""
    response = await stream_turn(
        session=async_db_session,
        user=user_fixture,
        thread_id=thread_fixture.id,
        body={"text": "hi", "attachments": [], "model": "gpt-4"},
    )
    chunks = []
    async for ch in response.body_iterator:
        chunks.append(ch if isinstance(ch, str) else ch.decode())
    combined = "".join(chunks)

    assert '"event_type":"item"' in combined
    assert '"event_type":"done"' in combined
