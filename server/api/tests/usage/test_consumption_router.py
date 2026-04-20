# server/api/tests/usage/test_consumption_router.py
import pytest
from httpx import AsyncClient, ASGITransport
from ai_portal.main import app


@pytest.mark.asyncio
async def test_summary_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/api/admin/consumption/summary",
            params={"start": "2026-01-01", "end": "2026-12-31"},
        )
    assert r.status_code in (401, 403), (
        f"Expected 401/403 (not 404=unregistered, not 200=open), got {r.status_code}"
    )


@pytest.mark.asyncio
async def test_trend_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/api/admin/consumption/trend",
            params={"start": "2026-01-01", "end": "2026-12-31", "grain": "day", "by": "model"},
        )
    assert r.status_code in (401, 403), (
        f"Expected 401/403 (not 404=unregistered, not 200=open), got {r.status_code}"
    )


@pytest.mark.asyncio
async def test_threads_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/api/admin/consumption/threads",
            params={"start": "2026-01-01", "end": "2026-12-31", "page": "1", "page_size": "10"},
        )
    assert r.status_code in (401, 403), (
        f"Expected 401/403 (not 404=unregistered, not 200=open), got {r.status_code}"
    )


@pytest.mark.asyncio
async def test_timeline_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/admin/consumption/threads/1/timeline")
    assert r.status_code in (401, 403), (
        f"Expected 401/403 (not 404=unregistered, not 200=open), got {r.status_code}"
    )
