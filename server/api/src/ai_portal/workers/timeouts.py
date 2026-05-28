"""Per-pool task wall-time timeout — config + enforcement.

Pool ``settings_json`` field:

.. code-block:: json

    {"default_wall_time_sec": 1800}

Bounds: 60 s ≤ wall_time ≤ 86 400 s (24 h). Out-of-range / non-int values
fall back to :data:`DEFAULT_WALL_TIME_SEC`.

Use :func:`resolve_wall_time` at run start to (a) pick the effective
deadline and (b) optionally write it into the sandbox :class:`ResourceLimits`
so the sandbox provider can enforce it via its own kill mechanism.

Use :func:`enforce_wall_time` to wrap the run coroutine; on overrun it
raises :class:`TaskTimedOut`, which the orchestrator translates into a
``status=failed, reason=timeout`` row via :func:`timeout_failure_payload`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, TypeVar

from ai_portal.workers.types import ResourceLimits, TaskStatus

DEFAULT_WALL_TIME_SEC = 1800  # 30 min
_MIN = 60
_MAX = 86_400

_T = TypeVar("_T")


class TaskTimedOut(Exception):
    """Run exceeded its wall-time budget."""

    def __init__(self, wall_time_sec: float) -> None:
        super().__init__(f"task exceeded wall_time_sec={wall_time_sec}")
        self.wall_time_sec = wall_time_sec


def resolve_wall_time(
    pool_settings: dict[str, Any],
    *,
    into: ResourceLimits | None = None,
) -> int:
    """Resolve the effective wall-time (in seconds) for a run."""
    raw = pool_settings.get("default_wall_time_sec")
    if not isinstance(raw, int) or isinstance(raw, bool):
        wall = DEFAULT_WALL_TIME_SEC
    else:
        wall = max(_MIN, min(_MAX, raw))
    if into is not None:
        into.wall_time_sec = wall
    return wall


async def enforce_wall_time(
    coro: Awaitable[_T],
    *,
    wall_time_sec: int,
    _min_for_test: float | None = None,
) -> _T:
    """Run ``coro`` under a wall-time deadline.

    ``_min_for_test`` overrides the deadline with a sub-second value so
    the timeout path is exercisable without slow tests.
    """
    deadline = float(_min_for_test) if _min_for_test is not None else float(wall_time_sec)
    try:
        return await asyncio.wait_for(coro, timeout=deadline)
    except asyncio.TimeoutError as e:
        raise TaskTimedOut(deadline) from e


def timeout_failure_payload(*, wall_time_sec: int) -> dict[str, Any]:
    """Payload to stamp on the run/task row when a timeout fires."""
    return {
        "status": TaskStatus.failed.value,
        "reason": "timeout",
        "wall_time_sec": wall_time_sec,
    }
