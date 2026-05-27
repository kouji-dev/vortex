"""NotifyService — fan-out dispatcher with per-user preference matrix.

Two entry points:
- ``send(channel=..., recipient=..., template_id=..., payload=...)`` — direct
  channel dispatch (used by I1 transactional flows that already know the wire)
- ``send_event(user_id=..., event_type=..., template_id=..., payload=...)`` —
  resolves the user's PrefMatrix, applies throttle/digest policy per
  event_type, and fans out to every enabled channel that has a recipient

For throttle mode ``digest``, repeat events inside the throttle window are
buffered. Call ``flush_digests()`` periodically (cron / background task) to
emit aggregated payloads for windows that have closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from ai_portal.notify.prefs import PrefMatrix
from ai_portal.notify.protocol import Channel


@dataclass(slots=True)
class _ThrottleState:
    last_sent_at: datetime
    window_start: datetime
    buffered: list[dict] = field(default_factory=list)
    template_id: str = ""


class NotifyService:
    def __init__(self, channels: Mapping[str, Channel]) -> None:
        self._channels = dict(channels)
        self._prefs: PrefMatrix | None = None
        # key: (user_id, event_type, channel) -> throttle state
        self._throttle: dict[tuple[int, str, str], _ThrottleState] = {}

    def register(self, name: str, channel: Channel) -> None:
        self._channels[name] = channel

    def has(self, name: str) -> bool:
        return name in self._channels

    def attach_prefs(self, prefs: PrefMatrix) -> None:
        self._prefs = prefs

    async def send(
        self,
        *,
        channel: str,
        recipient: str,
        template_id: str,
        payload: dict,
    ) -> None:
        if channel not in self._channels:
            raise KeyError(f"notify channel not registered: {channel!r}")
        await self._channels[channel].send(recipient, template_id, payload)

    async def send_event(
        self,
        *,
        user_id: int,
        event_type: str,
        template_id: str,
        payload: dict,
    ) -> None:
        """Resolve user prefs and fan out to enabled channels.

        Channels are skipped silently when:
        - user pref is disabled (or default = false and no row)
        - no recipient configured for that channel
        - throttle policy says "drop" and we're inside the window
        - throttle policy says "digest" and we're inside the window (buffered
          for flush)
        """
        if self._prefs is None:
            raise RuntimeError("notify: attach_prefs() before send_event()")

        prefs = self._prefs
        policy = prefs.policy_for(event_type)
        now = prefs.now()

        for channel_name in self._channels:
            if not prefs.is_enabled(user_id, event_type, channel_name):
                continue
            recipient = prefs.recipient_for(channel_name)
            if recipient is None:
                continue

            key = (user_id, event_type, channel_name)
            state = self._throttle.get(key)

            if (
                state is not None
                and (now - state.window_start) < policy.throttle_window
            ):
                # inside window
                if policy.mode == "drop":
                    continue
                if policy.mode == "digest":
                    state.buffered.append(payload)
                    state.template_id = template_id
                    continue

            await self._channels[channel_name].send(recipient, template_id, payload)
            self._throttle[key] = _ThrottleState(
                last_sent_at=now,
                window_start=now,
                buffered=[],
                template_id=template_id,
            )

    async def flush_digests(self) -> None:
        """Emit one aggregated send per (user, event, channel) whose window has
        closed and whose buffer is non-empty.

        Aggregated payload shape:
            {"digest_count": N, "events": [<original payloads>, ...]}
        """
        if self._prefs is None:
            return

        now = self._prefs.now()
        flushed: list[tuple[int, str, str]] = []

        for key, state in self._throttle.items():
            user_id, event_type, channel_name = key
            policy = self._prefs.policy_for(event_type)
            if policy.mode != "digest":
                continue
            if not state.buffered:
                continue
            if (now - state.window_start) < policy.throttle_window:
                continue

            recipient = self._prefs.recipient_for(channel_name)
            if recipient is None:
                state.buffered.clear()
                continue

            digest_payload = {
                "digest_count": len(state.buffered),
                "events": list(state.buffered),
            }
            await self._channels[channel_name].send(
                recipient, state.template_id, digest_payload
            )
            flushed.append(key)

        for key in flushed:
            self._throttle[key] = _ThrottleState(
                last_sent_at=now,
                window_start=now,
                buffered=[],
                template_id=self._throttle[key].template_id,
            )
