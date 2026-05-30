"""Pure-logic tests for the worker skills registry + bundled packages."""

from __future__ import annotations

import pytest

from ai_portal.workers.skills import (
    SkillPackage,
    get_skill,
    list_skills,
    register_skill,
    resolve_skills,
)
from ai_portal.workers.skills.registry import UnknownSkill


def test_bundled_skills_present() -> None:
    names = list_skills()
    for expected in ("fix-bug", "write-tests", "refactor", "dependency-update"):
        assert expected in names


def test_get_skill_returns_package() -> None:
    pkg = get_skill("fix-bug")
    assert pkg.name == "fix-bug"
    assert pkg.instructions.strip()  # non-empty caveman instructions


def test_get_unknown_skill_raises() -> None:
    with pytest.raises(UnknownSkill):
        get_skill("nope")


def test_resolve_skills_maps_names() -> None:
    pkgs = resolve_skills(["fix-bug", "refactor"])
    assert [p.name for p in pkgs] == ["fix-bug", "refactor"]


def test_resolve_skills_raises_on_unknown() -> None:
    with pytest.raises(UnknownSkill):
        resolve_skills(["fix-bug", "ghost"])


def test_skill_md_renders_name_and_description() -> None:
    pkg = get_skill("write-tests")
    md = pkg.skill_md()
    assert md.startswith("# write-tests")
    assert pkg.description in md


def test_register_custom_skill_roundtrips() -> None:
    custom = SkillPackage(
        name="org-convention",
        description="Follow ACME house style.",
        instructions="- Tabs not spaces.\n- 80 col.",
        applies_to=["python"],
    )
    register_skill(custom)
    try:
        assert "org-convention" in list_skills()
        assert get_skill("org-convention").description == "Follow ACME house style."
    finally:
        # keep the registry clean for other tests
        from ai_portal.workers.skills import registry as reg

        reg._REGISTRY.pop("org-convention", None)
