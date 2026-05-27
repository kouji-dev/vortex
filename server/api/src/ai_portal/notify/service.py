"""NotifyService — fan-out dispatcher.

Holds a name→Channel registry; routes ``send(channel=...)`` to the matching
implementation. Per-user preference resolution (see I3) lands later.
"""

from __future__ import annotations

from collections.abc import Mapping

from ai_portal.notify.protocol import Channel


class NotifyService:
    def __init__(self, channels: Mapping[str, Channel]) -> None:
        self._channels = dict(channels)

    def register(self, name: str, channel: Channel) -> None:
        self._channels[name] = channel

    def has(self, name: str) -> bool:
        return name in self._channels

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
