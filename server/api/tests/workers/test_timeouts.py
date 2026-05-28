"""Tests for per-pool task wall-time timeout helpers."""

from __future__ import annotations

import asyncio

import pytest

from ai_portal.workers.timeouts import (
    DEFAULT_WALL_TIME_SEC,
    TaskTimedOut,
    enforce_wall_time,
    resolve_wall_time,
)
from ai_portal.workers.types import ResourceLimits, TaskStatus


def test_resolve_wall_time_default_when_missing() -> None:
    assert resolve_wall_time({}) == DEFAULT_WALL_TIME_SEC


def test_resolve_wall_time_from_settings() -> None:
    assert resolve_wall_time({"default_wall_time_sec": 600}) == 600


def test_resolve_wall_time_clamps_to_min() -> None:
    assert resolve_wall_time({"default_wall_time_sec": 0}) >= 60


def test_resolve_wall_time_clamps_to_max() -> None:
    assert resolve_wall_time({"default_wall_time_sec": 999_999_999}) <= 86_400


def test_resolve_wall_time_ignores_non_int() -> None:
    assert resolve_wall_time({"default_wall_time_sec": "abc"}) == DEFAULT_WALL_TIME_SEC


def test_resolve_wall_time_writes_into_resource_limits() -> None:
    limits = ResourceLimits()
    new = resolve_wall_time({"default_wall_time_sec": 900}, into=limits)
    assert new == 900
    assert limits.wall_time_sec == 900


@pytest.mark.asyncio
async def test_enforce_wall_time_returns_when_completes_in_time() -> None:
    async def _quick():
        await asyncio.sleep(0.01)
        return "ok"

    out = await enforce_wall_time(_quick(), wall_time_sec=1)
    assert out == "ok"


@pytest.mark.asyncio
async def test_enforce_wall_time_raises_on_overrun() -> None:
    async def _slow():
        await asyncio.sleep(0.2)
        return "ok"

    with pytest.raises(TaskTimedOut) as ei:
        # ``wall_time_sec`` is the public seconds knob; we pass ``_min`` to
        # test the kill path with a sub-second deadline.
        await enforce_wall_time(_slow(), wall_time_sec=1, _min_for_test=0.05)
    assert ei.value.wall_time_sec == 0.05


def test_failed_status_marker_payload() -> None:
    from ai_portal.workers.timeouts import timeout_failure_payload

    p = timeout_failure_payload(wall_time_sec=900)
    assert p["status"] == TaskStatus.failed.value
    assert p["reason"] == "timeout"
    assert p["wall_time_sec"] == 900
