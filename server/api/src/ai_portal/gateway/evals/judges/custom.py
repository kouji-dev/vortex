"""Custom-judge registry + verdict shape.

The verdict shape is shared across all judges so the runner can flatten
to a single per-record outcome.

Custom judges are async callables registered by name via
:func:`register_custom_judge`. The record's ``config["name"]`` selects
which custom judge runs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """Outcome of a single judge call."""

    passed: bool
    detail: str = ""


CustomJudge = Callable[[str, str, dict[str, Any]], Awaitable[JudgeVerdict]]
"""Signature: ``async (output, expected, config) -> JudgeVerdict``."""


_REGISTRY: dict[str, CustomJudge] = {}


def register_custom_judge(name: str, judge: CustomJudge) -> None:
    """Install a custom judge under ``name``.

    Overwrites silently — call sites are tests and one-shot wiring at
    import time.
    """
    _REGISTRY[name] = judge


def get_custom_judge(name: str) -> CustomJudge | None:
    return _REGISTRY.get(name)


async def custom_judge(
    *, output: str, expected: str, config: dict[str, Any]
) -> JudgeVerdict:
    """Dispatch to the registered judge named in ``config["name"]``."""
    name = str(config.get("name") or "").strip()
    if not name:
        return JudgeVerdict(passed=False, detail="custom judge: missing config.name")
    judge = get_custom_judge(name)
    if judge is None:
        return JudgeVerdict(
            passed=False, detail=f"custom judge {name!r} not registered"
        )
    try:
        return await judge(output, expected, config)
    except Exception as exc:  # noqa: BLE001
        return JudgeVerdict(passed=False, detail=f"custom judge error: {exc}")


__all__ = [
    "CustomJudge",
    "JudgeVerdict",
    "custom_judge",
    "get_custom_judge",
    "register_custom_judge",
]
