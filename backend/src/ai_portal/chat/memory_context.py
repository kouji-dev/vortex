"""Memory integration — builds the user-memory block for the system prompt."""

from __future__ import annotations

from ai_portal.memory.model import UserMemory


def build_memory_block(
    *,
    system_profile: UserMemory | None,
    manual_memories: list[UserMemory],
) -> str:
    """Combine the auto-generated system profile and manually saved memories.

    ``system_profile`` is the single ``is_system=True`` row (may be None).
    ``manual_memories`` contains all other active memory rows for the user.
    Returns an empty string when no durable memory is available.
    """
    parts: list[str] = []

    if (
        system_profile is not None
        and (system_profile.content or "").strip()
        and system_profile.is_active
    ):
        parts.append(
            "User profile (auto-updated from your conversations):\n"
            + system_profile.content.strip()
        )

    manuals = [
        m
        for m in manual_memories
        if m.is_active and not m.is_system and (m.content or "").strip()
    ]
    if manuals:
        lines = "\n".join(f"- {m.content.strip()}" for m in manuals)
        parts.append(f"Memories the user saved manually:\n{lines}")

    if not parts:
        return ""
    return "What you know about this user:\n\n" + "\n\n".join(parts)
