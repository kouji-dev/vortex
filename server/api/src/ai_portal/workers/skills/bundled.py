"""Bundled starter skills (fix-bug / write-tests / refactor / dependency-update).

Instructions are caveman style per project rules: short imperatives, tell the
agent what to DO, no filler. Org-custom skills register alongside these.
"""

from __future__ import annotations

from ai_portal.workers.skills.protocol import SkillPackage

FIX_BUG = SkillPackage(
    name="fix-bug",
    description="Reproduce, locate, and fix a reported bug with a regression test.",
    instructions=(
        "- Reproduce the bug first. Write a failing test that captures it.\n"
        "- Find root cause. Read surrounding code before editing.\n"
        "- Fix minimally. No unrelated refactors.\n"
        "- Run the failing test — confirm it passes. Run the full suite.\n"
        "- Commit: `fix: <summary>`. Reference the issue."
    ),
    applies_to=["python", "node", "go", "rust", "polyglot"],
)

WRITE_TESTS = SkillPackage(
    name="write-tests",
    description="Add focused tests for the target code path.",
    instructions=(
        "- Detect the project's test runner first. Use it.\n"
        "- Cover happy path + edge cases + error path.\n"
        "- One behavior per test. Clear names.\n"
        "- No network/disk in unit tests. Mock external calls.\n"
        "- Run new tests. Confirm green. Commit: `test: <summary>`."
    ),
    applies_to=["python", "node", "go", "rust", "polyglot"],
)

REFACTOR = SkillPackage(
    name="refactor",
    description="Restructure code without changing behavior.",
    instructions=(
        "- Confirm tests exist and pass BEFORE refactoring. Add them if missing.\n"
        "- Change structure only. No behavior change.\n"
        "- Small steps. Run tests after each.\n"
        "- Keep public signatures stable unless asked.\n"
        "- Commit: `refactor: <summary>`."
    ),
    applies_to=["python", "node", "go", "rust", "polyglot"],
)

DEPENDENCY_UPDATE = SkillPackage(
    name="dependency-update",
    description="Bump dependencies and fix resulting breakage.",
    instructions=(
        "- Update lockfile via the project's package manager. No manual edits.\n"
        "- Read changelogs for major bumps. Migrate breaking changes.\n"
        "- Run build + full test suite. Fix failures.\n"
        "- One PR per logical bump group.\n"
        "- Commit: `chore(deps): <summary>`."
    ),
    applies_to=["python", "node", "go", "rust", "polyglot"],
)

ALL_BUNDLED: list[SkillPackage] = [FIX_BUG, WRITE_TESTS, REFACTOR, DEPENDENCY_UPDATE]
