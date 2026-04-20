# server/api/tests/chat/test_repository.py
"""Tests for the Thread + ThreadItem repository functions."""

from __future__ import annotations

from tests.conftest import requires_postgres
from ai_portal.chat import repository


@requires_postgres
def test_list_thread_items_returns_ordered_by_created_at(db_session, thread_with_items):
    items = repository.list_thread_items(
        db_session,
        thread_id=thread_with_items.id,
        org_id=thread_with_items.org_id,
    )
    assert len(items) == 3  # user_message, assistant_text, turn_end
    ts = [i.created_at for i in items]
    assert ts == sorted(ts)


@requires_postgres
def test_list_thread_items_since_id(db_session, thread_with_items):
    all_items = repository.list_thread_items(
        db_session,
        thread_id=thread_with_items.id,
        org_id=thread_with_items.org_id,
    )
    mid_id = all_items[0].id
    tail = repository.list_thread_items(
        db_session,
        thread_id=thread_with_items.id,
        org_id=thread_with_items.org_id,
        since_id=mid_id,
    )
    assert all(i.id > mid_id for i in tail)
    assert len(tail) == 2  # assistant_text, turn_end


@requires_postgres
def test_get_thread_item_returns_correct_item(db_session, thread_with_items):
    all_items = repository.list_thread_items(
        db_session,
        thread_id=thread_with_items.id,
        org_id=thread_with_items.org_id,
    )
    first = all_items[0]
    fetched = repository.get_thread_item(
        db_session,
        item_id=first.id,
        org_id=thread_with_items.org_id,
    )
    assert fetched is not None
    assert fetched.id == first.id


@requires_postgres
def test_count_thread_items(db_session, thread_with_items):
    count = repository.count_thread_items(
        db_session,
        thread_id=thread_with_items.id,
        org_id=thread_with_items.org_id,
    )
    assert count == 3


@requires_postgres
def test_get_thread(db_session, thread_with_items):
    fetched = repository.get_thread(
        db_session,
        thread_id=thread_with_items.id,
        org_id=thread_with_items.org_id,
    )
    assert fetched is not None
    assert fetched.id == thread_with_items.id
    assert fetched.title == "test thread"


@requires_postgres
def test_list_thread_items_wrong_org_returns_empty(db_session, thread_with_items):
    import uuid
    other_org = uuid.uuid4()
    items = repository.list_thread_items(
        db_session,
        thread_id=thread_with_items.id,
        org_id=other_org,
    )
    assert items == []
