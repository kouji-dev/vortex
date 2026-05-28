"""Multi-turn conversational rewrite.

When prior chat turns are supplied, rewrite the current user question into a
standalone query that resolves coreferences ("it", "that"). The rewrite goes
through the Gateway facade when available; otherwise the most recent user
turn is concatenated with the new question as a cheap fallback.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ChatTurn:
    role: str  # "user" | "assistant"
    text: str


def rewrite_question(
    question: str,
    prior_turns: list[ChatTurn] | None = None,
    *,
    model: str = "gpt-4o-mini",
    complete_fn=None,
) -> str:
    """Return a standalone version of ``question`` resolving prior context.

    `complete_fn` is an injectable callable: (system, user, model) -> str.
    When omitted, the function tries `ai_portal.gateway.complete` then falls
    back to a heuristic concatenation.
    """
    if not prior_turns:
        return question.strip()

    convo = "\n".join(f"{t.role}: {t.text}" for t in prior_turns[-6:])
    system = (
        "Rewrite question.\n"
        "- Replace pronouns with referents from prior turns.\n"
        "- Keep wording terse. No preamble. Single sentence."
    )
    user = f"Prior turns:\n{convo}\n\nNew question: {question}\nRewritten:"

    fn = complete_fn or _default_complete
    try:
        out = fn(system, user, model)
        if out and out.strip():
            return out.strip()
    except Exception:  # noqa: BLE001
        log.warning("rewrite failed; falling back", exc_info=True)

    # Heuristic: prepend last user turn for context-rich retrieval.
    last_user = next(
        (t.text for t in reversed(prior_turns) if t.role == "user"), ""
    )
    if last_user:
        return f"{last_user} {question}".strip()
    return question.strip()


def _default_complete(system: str, user: str, model: str) -> str:
    try:  # pragma: no cover - gateway facade absent in this branch
        from ai_portal.gateway import complete as gw_complete  # type: ignore

        res = gw_complete(model=model, system=system, user=user)
        return getattr(res, "text", str(res))
    except Exception:  # noqa: BLE001
        raise
