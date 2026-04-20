# tests/chat/streaming/test_context_assembler.py
import uuid
from decimal import Decimal

import pytest

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.model import ThreadItem
from ai_portal.chat.streaming.context_assembler import build_provider_messages


@pytest.fixture
async def populated_thread(async_db_session, thread_fixture, org_fixture):
    """Create a thread with a user message and assistant response."""
    turn = uuid.uuid4()
    user_item = ThreadItem(
        thread_id=thread_fixture.id, org_id=org_fixture.id, turn_id=turn,
        kind=ItemKind.user_message, role=ItemRole.user, status=ItemStatus.done,
        data={"text": "Hello world", "attachments": []},
    )
    async_db_session.add(user_item)
    await async_db_session.flush()

    asst_item = ThreadItem(
        thread_id=thread_fixture.id, org_id=org_fixture.id, turn_id=turn,
        kind=ItemKind.assistant_text, role=ItemRole.assistant, status=ItemStatus.done,
        data={"text": "Hi there!"},
    )
    async_db_session.add(asst_item)
    await async_db_session.flush()
    return thread_fixture


async def test_build_messages_includes_system_and_history(async_db_session, populated_thread, org_fixture):
    messages = await build_provider_messages(
        session=async_db_session,
        thread_id=populated_thread.id,
        org_id=org_fixture.id,
        system_prompt="You are helpful.",
        window_size=100,
    )
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are helpful."
    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles


async def test_window_size_truncates_history(async_db_session, thread_fixture, org_fixture):
    """With window_size=1, only the last 1 non-system message is kept."""
    turn1 = uuid.uuid4()
    turn2 = uuid.uuid4()
    for turn, text in [(turn1, "First"), (turn2, "Second")]:
        async_db_session.add(ThreadItem(
            thread_id=thread_fixture.id, org_id=org_fixture.id, turn_id=turn,
            kind=ItemKind.user_message, role=ItemRole.user, status=ItemStatus.done,
            data={"text": text, "attachments": []},
        ))
    await async_db_session.flush()

    messages = await build_provider_messages(
        session=async_db_session,
        thread_id=thread_fixture.id,
        org_id=org_fixture.id,
        system_prompt="System.",
        window_size=1,
    )
    # System + at most 1 non-system
    assert len(messages) <= 2
    assert messages[0]["role"] == "system"
