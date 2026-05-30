"""Skill registry — name → SkillPackage. Bundled starter set + org-custom.

Mirrors the sandbox/git/tools registry pattern. ``resolve_skills`` turns a
worker/pool's selected skill names into packages the runner materializes into
the sandbox.
"""

from __future__ import annotations

from ai_portal.workers.skills.bundled import ALL_BUNDLED
from ai_portal.workers.skills.protocol import SkillPackage

_REGISTRY: dict[str, SkillPackage] = {pkg.name: pkg for pkg in ALL_BUNDLED}


class UnknownSkill(KeyError):
    """Requested skill name is not registered."""


def register_skill(pkg: SkillPackage) -> None:
    """Register an org-custom skill (or override a bundled one)."""
    _REGISTRY[pkg.name] = pkg


def get_skill(name: str) -> SkillPackage:
    pkg = _REGISTRY.get(name)
    if pkg is None:
        raise UnknownSkill(name)
    return pkg


def list_skills() -> list[str]:
    return sorted(_REGISTRY)


def resolve_skills(names: list[str]) -> list[SkillPackage]:
    """Resolve selected skill names → packages. Raises on unknown names."""
    return [get_skill(n) for n in names]
