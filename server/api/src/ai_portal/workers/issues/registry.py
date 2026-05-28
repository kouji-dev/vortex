"""Issue-tracker registry — name → tracker lookup."""

from __future__ import annotations

from ai_portal.workers.issues.protocol import IssueTracker


class IssueTrackerNotRegistered(KeyError):
    """Raised when ``get(name)`` finds no tracker."""


_REG: dict[str, IssueTracker] = {}


def register(tracker: IssueTracker) -> None:
    _REG[tracker.name] = tracker


def get(name: str) -> IssueTracker:
    try:
        return _REG[name]
    except KeyError as e:
        raise IssueTrackerNotRegistered(name) from e


def all_trackers() -> list[str]:
    return list(_REG.keys())


def clear() -> None:
    _REG.clear()
