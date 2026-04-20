# tests/chat/streaming/test_turn_setup.py
import uuid

import pytest

from ai_portal.chat.item_kinds import ItemKind, ItemStatus
from ai_portal.chat.model import ThreadItem
from ai_portal.chat.streaming.turn_setup import new_turn, regenerate_turn, start_or_regenerate, TurnContext
from sqlalchemy import select


async def test_new_turn_creates_user_message_item(async_db_session, thread_fixture, org_fixture):
    context = await new_turn(
        session=async_db_session,
        thread=thread_fixture,
        user_text="Hello!",
        attachments=[],
        org_id=org_fixture.id,
    )
    assert isinstance(context, TurnContext)
    assert context.user_text == "Hello!"
    assert context.turn_id is not None

    # Verify a user_message item was created
    stmt = select(ThreadItem).where(
        ThreadItem.thread_id == thread_fixture.id,
        ThreadItem.turn_id == context.turn_id,
        ThreadItem.kind == ItemKind.user_message,
    )
    item = (await async_db_session.execute(stmt)).scalar_one_or_none()
    assert item is not None
    assert item.data["text"] == "Hello!"
    assert item.status == ItemStatus.done


async def test_regenerate_turn_returns_context_without_inserting(async_db_session, thread_fixture, org_fixture):
    existing_turn_id = uuid.uuid4()
    context = await regenerate_turn(
        session=async_db_session,
        thread=thread_fixture,
        turn_id=existing_turn_id,
        user_text="Old question",
        org_id=org_fixture.id,
    )
    assert context.turn_id == existing_turn_id
    assert context.user_text == "Old question"

    # No new user_message item should be created
    stmt = select(ThreadItem).where(
        ThreadItem.thread_id == thread_fixture.id,
        ThreadItem.turn_id == existing_turn_id,
        ThreadItem.kind == ItemKind.user_message,
    )
    item = (await async_db_session.execute(stmt)).scalar_one_or_none()
    assert item is None


async def test_start_or_regenerate_new_turn_path(async_db_session, thread_fixture, org_fixture):
    """start_or_regenerate with no regenerate_from_turn_id behaves like new_turn."""
    context = await start_or_regenerate(
        session=async_db_session,
        thread=thread_fixture,
        user_text="New message",
        attachments=[],
        org_id=org_fixture.id,
        regenerate_from_turn_id=None,
    )
    assert isinstance(context, TurnContext)
    assert context.user_text == "New message"
    assert context.turn_id is not None

    # A user_message item must have been inserted
    stmt = select(ThreadItem).where(
        ThreadItem.thread_id == thread_fixture.id,
        ThreadItem.turn_id == context.turn_id,
        ThreadItem.kind == ItemKind.user_message,
    )
    item = (await async_db_session.execute(stmt)).scalar_one_or_none()
    assert item is not None
    assert item.data["text"] == "New message"


async def test_start_or_regenerate_regenerate_path(async_db_session, thread_fixture, org_fixture):
    """start_or_regenerate with a turn_id behaves like regenerate_turn (no DB insert)."""
    existing_turn_id = uuid.uuid4()
    context = await start_or_regenerate(
        session=async_db_session,
        thread=thread_fixture,
        user_text="Previous question",
        attachments=[],
        org_id=org_fixture.id,
        regenerate_from_turn_id=existing_turn_id,
    )
    assert context.turn_id == existing_turn_id
    assert context.user_text == "Previous question"

    # No new user_message item should be created
    stmt = select(ThreadItem).where(
        ThreadItem.thread_id == thread_fixture.id,
        ThreadItem.turn_id == existing_turn_id,
        ThreadItem.kind == ItemKind.user_message,
    )
    item = (await async_db_session.execute(stmt)).scalar_one_or_none()
    assert item is None
