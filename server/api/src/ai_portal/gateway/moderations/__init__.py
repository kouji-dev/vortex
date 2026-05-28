"""Moderation — score input text across harm categories.

Public surface:

- :class:`Moderator` (Protocol)
- :class:`ModerationResult` — one item's verdict
- Bundled providers live in :mod:`.providers`
"""

from ai_portal.gateway.moderations.protocol import (
    ModerationResult,
    Moderator,
    CATEGORIES,
)

__all__ = ["Moderator", "ModerationResult", "CATEGORIES"]
