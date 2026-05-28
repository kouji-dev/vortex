"""Guardrails — pre/post-LLM scans (prompt injection, moderation, PII, …).

Public surface:

- :class:`Guardrail` (Protocol)
- :class:`Verdict` — outcome of a scan
- :class:`Hit` — one detection
- Bundled providers live in :mod:`.providers`
"""

from ai_portal.gateway.guardrails.protocol import (
    Action,
    Guardrail,
    Hit,
    Verdict,
    clean,
)

__all__ = ["Guardrail", "Verdict", "Hit", "Action", "clean"]
