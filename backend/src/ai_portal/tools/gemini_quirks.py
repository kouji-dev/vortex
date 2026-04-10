"""Gemini-specific tool-calling quirks and workarounds.

Known issues handled here:
- Flash Lite streaming bug: returns finish_reason="stop" instead of "tool_calls"
  even when a tool call was made, causing the loop to exit without executing the tool.
- Small/lite models ignore tool instructions entirely when tool_choice defaults to AUTO.
  Fix: force tool_choice="any" on the first LLM iteration so the model must call a tool.
- After tool results are injected, tool_choice must be dropped (None) so the model
  can synthesize a final text answer — forcing "any" on every iteration would loop forever.
"""

from __future__ import annotations

# Models known to need forced tool_choice on the first iteration.
# These models regularly skip tool calls when tool_choice defaults to AUTO.
_FORCE_TOOL_CHOICE_MODELS = {
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-lite-preview",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-8b",
}


def needs_forced_tool_choice(model_id: str) -> bool:
    """Return True if this model needs tool_choice='any' on the first tool-call iteration."""
    normalized = model_id.lower().strip()
    # Strip catalog prefix (e.g. "google-gemini-3.1-flash-lite-preview" → "gemini-3.1-flash-lite-preview")
    for prefix in ("google-gemini-", "google/gemini-"):
        if normalized.startswith(prefix):
            normalized = "gemini-" + normalized[len(prefix):]
            break
    return normalized in _FORCE_TOOL_CHOICE_MODELS


def tool_choice_for_iteration(model_id: str, iteration: int, has_tools: bool) -> str | None:
    """
    Return the tool_choice value to pass to bind_tools() for this iteration.

    - iteration 0, lite model, tools present → "any"  (force a tool call)
    - iteration 0, capable model             → None   (let model decide via AUTO)
    - iteration > 0                          → None   (model should synthesize answer)
    - no tools                               → None
    """
    if not has_tools:
        return None
    if iteration == 0 and needs_forced_tool_choice(model_id):
        return "any"
    return None
