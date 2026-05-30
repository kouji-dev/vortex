"""Skill protocol + package shape.

A skill is data, not behavior: an instruction block (caveman style) plus
optional helper scripts, injected into the agent SDK's context. The runtime
materializes it into the sandbox as a ``SKILL.md`` (+ scripts) the agent can
load on demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SkillPackage:
    """Materializable skill payload (what gets written into the sandbox).

    ``files`` maps a relative path under the skill dir → file contents. The
    runner writes these next to ``SKILL.md`` so the agent can run helper
    scripts the skill ships.
    """

    name: str
    description: str
    instructions: str
    applies_to: list[str] = field(default_factory=list)  # e.g. ["python","node"]
    files: dict[str, str] = field(default_factory=dict)

    def skill_md(self) -> str:
        """Render the SKILL.md the agent SDK loads (name + description front,
        instructions body)."""
        return (
            f"# {self.name}\n\n"
            f"{self.description}\n\n"
            f"{self.instructions.strip()}\n"
        )


@runtime_checkable
class Skill(Protocol):
    """Contract a skill provider satisfies (bundled or org-custom)."""

    name: str

    def package(self) -> SkillPackage: ...
