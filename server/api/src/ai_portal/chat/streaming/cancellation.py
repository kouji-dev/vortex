"""cancellation — per-turn cancel token registry.

Allows an HTTP cancel endpoint to signal the streaming loop to stop.
"""

from __future__ import annotations

import logging
import uuid
from typing import ClassVar

logger = logging.getLogger(__name__)


class CancelToken:
    """A simple cancellation flag that can be checked by the streaming loop."""

    def __init__(self, turn_id: uuid.UUID) -> None:
        self.turn_id = turn_id
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True
        logger.info("cancel_token: cancelled turn_id=%s", self.turn_id)


class CancelRegistry:
    """Global registry mapping turn_id → CancelToken.

    Thread-safe for single-process deployments. In multi-process deployments,
    a Redis-backed alternative should be used.
    """

    _registry: ClassVar[dict[uuid.UUID, CancelToken]] = {}

    @classmethod
    def register(cls, turn_id: uuid.UUID) -> CancelToken:
        """Register a new turn and return its cancel token."""
        token = CancelToken(turn_id)
        cls._registry[turn_id] = token
        logger.debug("cancel_registry: registered turn_id=%s", turn_id)
        return token

    @classmethod
    def cancel(cls, turn_id: uuid.UUID) -> bool:
        """Signal cancellation for a turn. Returns True if the turn was found."""
        token = cls._registry.get(turn_id)
        if token is None:
            logger.warning("cancel_registry: unknown turn_id=%s", turn_id)
            return False
        token.cancel()
        return True

    @classmethod
    def unregister(cls, turn_id: uuid.UUID) -> None:
        """Remove a turn from the registry (called when streaming completes)."""
        cls._registry.pop(turn_id, None)
        logger.debug("cancel_registry: unregistered turn_id=%s", turn_id)

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (for testing)."""
        cls._registry.clear()


# ---------------------------------------------------------------------------
# Module-level aliases (spec contract)
# ---------------------------------------------------------------------------


def register_turn(turn_id: uuid.UUID) -> CancelToken:
    """Register a turn and return its cancel token."""
    return CancelRegistry.register(turn_id)


def release_turn(turn_id: uuid.UUID) -> None:
    """Remove a turn from the registry when streaming completes."""
    CancelRegistry.unregister(turn_id)


async def cancel_turn(
    *,
    turn_id: uuid.UUID,
) -> bool:
    """Trip the in-process cancel token for a turn. Returns True if found."""
    return CancelRegistry.cancel(turn_id)
