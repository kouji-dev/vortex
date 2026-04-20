# server/api/tests/chat/streaming/test_item_writer.py
import uuid
from decimal import Decimal

import pytest

from ai_portal.chat.item_kinds import ItemKind, ItemStatus
from ai_portal.chat.streaming.item_writer import IllegalTransition, ItemWriter


@pytest.fixture
async def writer(async_db_session, thread_fixture):
    return ItemWriter(session=async_db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id)


async def test_start_and_finish_llm_call(writer):
    turn = uuid.uuid4()
    item = await writer.start_llm_call(turn_id=turn, model="gpt-4", iteration_index=0)
    assert item.status == ItemStatus.streaming
    done = await writer.finish_llm_call(
        item_id=item.id, input_tokens=10, output_tokens=20,
        cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
        cost_usd=Decimal("0.001"), cost_estimated=False,
    )
    assert done.status == ItemStatus.done
    assert done.cost_usd == Decimal("0.001")


async def test_cannot_finish_already_finished_llm_call(writer):
    turn = uuid.uuid4()
    item = await writer.start_llm_call(turn_id=turn, model="gpt-4", iteration_index=0)
    await writer.finish_llm_call(
        item_id=item.id, input_tokens=1, output_tokens=1,
        cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
        cost_usd=Decimal("0"), cost_estimated=True,
    )
    with pytest.raises(IllegalTransition):
        await writer.finish_llm_call(
            item_id=item.id, input_tokens=1, output_tokens=1,
            cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
            cost_usd=Decimal("0"), cost_estimated=True,
        )


async def test_append_text_delta_then_finalize(writer):
    turn = uuid.uuid4()
    item = await writer.start_text(turn_id=turn)
    await writer.append_text_delta(item.id, "hel")
    await writer.append_text_delta(item.id, "lo")
    final = await writer.finalize_text(item.id)
    assert final.status == ItemStatus.done
    assert final.data["text"] == "hello"


async def test_start_and_finish_tool_call_records_cost(writer):
    turn = uuid.uuid4()
    item = await writer.start_tool_call(turn_id=turn, tool_name="web_search", provider="tavily", params={"q": "x"})
    done = await writer.finish_tool_call(
        item_id=item.id, result_snippet="ok", error=None,
        cost_usd=Decimal("0.008"), cost_estimated=True, latency_ms=340,
    )
    assert done.status == ItemStatus.done
    assert done.cost_usd == Decimal("0.008")
    assert done.latency_ms == 340


async def test_cancel_turn_flips_streaming_items(writer, async_db_session):
    turn = uuid.uuid4()
    item = await writer.start_llm_call(turn_id=turn, model="gpt-4", iteration_index=0)
    await writer.cancel_turn_items(turn_id=turn, partial_cost=Decimal("0.0001"))
    await async_db_session.refresh(item)
    assert item.status == ItemStatus.cancelled
    assert item.cost_usd == Decimal("0.0001")


async def test_sweep_stale_streaming_marks_error(writer, async_db_session):
    from datetime import datetime, timezone, timedelta
    turn = uuid.uuid4()
    item = await writer.start_llm_call(turn_id=turn, model="gpt-4", iteration_index=0)
    item.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await async_db_session.flush()
    count = await writer.sweep_stale(older_than_seconds=60)
    assert count >= 1
    await async_db_session.refresh(item)
    assert item.status == ItemStatus.error
    assert item.data.get("error") == "interrupted"
