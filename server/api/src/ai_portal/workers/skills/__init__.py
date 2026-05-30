"""Agent skills — reusable capability packages injected into the agent SDK.

We customize worker behavior by injecting **skills** into the running agent's
context — NOT by writing a custom agent loop (the SDK has its own loop, see
spec "Agent Skills"). A skill = ``{name, description, instructions, optional
scripts/tools, applies_to}``.

The in-sandbox runner installs the selected skills into the agent's filesystem
before/at launch (Claude Agent SDK loads them via ``setting_sources`` + the
``Skill`` tool; Codex via its skills mechanism — verify per-SDK at impl).
"""

from __future__ import annotations

from ai_portal.workers.skills.protocol import Skill, SkillPackage
from ai_portal.workers.skills.registry import (
    UnknownSkill,
    get_skill,
    list_skills,
    register_skill,
    resolve_skills,
)

__all__ = [
    "Skill",
    "SkillPackage",
    "UnknownSkill",
    "get_skill",
    "list_skills",
    "register_skill",
    "resolve_skills",
]
