"""Per-user notification preference matrix + throttle/digest policies.

PrefMatrix is the resolver passed to ``NotifyService.attach_prefs(...)``:
- ``prefs[(user_id, event_type, channel)] = bool`` — explicit user toggle
- ``defaults[event_type][channel] = bool`` — platform default when no user row
- ``recipients[channel] = str`` — per-user destination for that channel
- ``policies[event_type] = EventPolicy`` — throttle window + mode

Production callers construct a fresh PrefMatrix per dispatch by reading the
``user_notification_prefs`` table and the user's contact rows; tests use
in-memory dicts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

ThrottleMode = Literal["drop", "digest"]


@dataclass(slots=True, frozen=True)
class EventPolicy:
    """Throttle policy for a given event_type.

    - ``throttle_window``: window inside which duplicates are coalesced
    - ``mode``:
        - ``"drop"``: silently discard duplicates inside the window
        - ``"digest"``: hold duplicates; flush_digests() emits one aggregated
          payload after the window closes
    """

    throttle_window: timedelta = timedelta(0)
    mode: ThrottleMode = "drop"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PrefMatrix:
    """User preference resolver.

    ``recipients`` maps channel_name → recipient string for the one user this
    matrix represents. For multi-user dispatch, construct a separate matrix per
    user (or fetch a per-user view inside the service).
    """

    prefs: dict[tuple[int, str, str], bool] = field(default_factory=dict)
    defaults: dict[str, dict[str, bool]] = field(default_factory=dict)
    recipients: dict[str, str] = field(default_factory=dict)
    policies: dict[str, EventPolicy] = field(default_factory=dict)
    clock: Callable[[], datetime] = _utcnow

    def is_enabled(self, user_id: int, event_type: str, channel: str) -> bool:
        explicit = self.prefs.get((user_id, event_type, channel))
        if explicit is not None:
            return explicit
        return self.defaults.get(event_type, {}).get(channel, False)

    def recipient_for(self, channel: str) -> str | None:
        return self.recipients.get(channel)

    def policy_for(self, event_type: str) -> EventPolicy:
        return self.policies.get(event_type, EventPolicy())

    def now(self) -> datetime:
        return self.clock()
