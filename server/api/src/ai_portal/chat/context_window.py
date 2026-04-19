"""Conversation context windowing.

Determines when to trigger summarization and which slice of the message history
to include in the LLM context window.
"""

from __future__ import annotations


def should_summarize(
    *,
    message_count: int,
    base_window: int,
    summary_interval: int,
) -> bool:
    """Return True when a background summarization pass should be triggered.

    Summarization fires once the history exceeds ``base_window``, then again
    every ``summary_interval`` messages beyond that threshold.
    """
    if message_count <= base_window:
        return False
    excess = message_count - base_window
    return excess == 1 or excess % summary_interval == 0


def slice_window_messages(
    messages: list[dict],
    *,
    base_window: int,
    summary_interval: int,
    has_summary: bool,
) -> list[dict]:
    """Trim the message list to the active context window.

    - Fits within ``base_window``: return as-is.
    - Exceeds window, no summary yet: keep the latest ``base_window`` messages.
    - Has a rolling summary: keep only the latest ``summary_interval`` messages
      (the rest are covered by the summary injected into the system prompt).
    """
    if len(messages) <= base_window:
        return messages
    if not has_summary:
        return messages[-base_window:]
    return messages[-summary_interval:]
