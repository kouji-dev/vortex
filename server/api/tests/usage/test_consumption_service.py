# server/api/tests/usage/test_consumption_service.py
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from ai_portal.usage import consumption_service


@pytest.mark.asyncio
async def test_summary_aggregates_by_model(async_db_session, thread_items_fixture):
    res = await consumption_service.summary(
        session=async_db_session, org_id=thread_items_fixture.org_id,
        start=datetime.now(timezone.utc) - timedelta(days=30),
        end=datetime.now(timezone.utc),
    )
    models = {r.key for r in res.by_model}
    assert "gpt-4" in models


@pytest.mark.asyncio
async def test_summary_kpis_include_month_spend(async_db_session, thread_items_fixture):
    res = await consumption_service.summary(
        session=async_db_session, org_id=thread_items_fixture.org_id,
        start=datetime.now(timezone.utc) - timedelta(days=30),
        end=datetime.now(timezone.utc),
    )
    labels = [k.label for k in res.kpis]
    assert "Month spend" in labels
    assert "Messages streamed" in labels


@pytest.mark.asyncio
async def test_trend_day_grain(async_db_session, thread_items_fixture):
    res = await consumption_service.trend(
        session=async_db_session, org_id=thread_items_fixture.org_id,
        start=datetime.now(timezone.utc) - timedelta(days=90),
        end=datetime.now(timezone.utc), grain="day", by="kind",
    )
    assert len(res.series) >= 1
    assert res.grain == "day"


@pytest.mark.asyncio
async def test_threads_paginated(async_db_session, thread_items_fixture):
    res = await consumption_service.threads(
        session=async_db_session, org_id=thread_items_fixture.org_id,
        start=datetime.now(timezone.utc) - timedelta(days=90),
        end=datetime.now(timezone.utc), user_id=None, model=None, page=1, page_size=10,
    )
    assert res.total == 1
    assert len(res.rows) <= 10


@pytest.mark.asyncio
async def test_timeline_for_thread(async_db_session, thread_items_fixture):
    res = await consumption_service.timeline(
        session=async_db_session, org_id=thread_items_fixture.org_id,
        thread_id=thread_items_fixture.id,
    )
    assert res.thread_id == thread_items_fixture.id
    assert all(i.created_at is not None for i in res.items)
