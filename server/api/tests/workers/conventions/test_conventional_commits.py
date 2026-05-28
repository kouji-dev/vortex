"""Conventional Commits enforcement — validate commit subject lines."""

from __future__ import annotations

import pytest

from ai_portal.workers.conventions.conventional_commits import (
    ConventionalCommitError,
    validate_commit_message,
)


def test_accepts_feat_subject():
    validate_commit_message("feat(workers): ReAct agent loop")


def test_accepts_fix_no_scope():
    validate_commit_message("fix: handle nil pointer")


def test_accepts_breaking_marker():
    validate_commit_message("feat(api)!: drop legacy endpoint")


def test_rejects_missing_type():
    with pytest.raises(ConventionalCommitError):
        validate_commit_message("just changed stuff")


def test_rejects_unknown_type():
    with pytest.raises(ConventionalCommitError):
        validate_commit_message("nope: something")


def test_rejects_blank():
    with pytest.raises(ConventionalCommitError):
        validate_commit_message("")


def test_rejects_too_long():
    with pytest.raises(ConventionalCommitError):
        validate_commit_message("feat: " + "x" * 200)


def test_custom_allowed_types():
    validate_commit_message(
        "wip: scaffold thing", allowed_types=("wip", "feat")
    )
    with pytest.raises(ConventionalCommitError):
        validate_commit_message(
            "chore: x", allowed_types=("wip", "feat")
        )


def test_first_body_line_is_validated():
    # Only the subject line gets validated.
    validate_commit_message(
        "feat(workers): subject\n\nbody can be free form."
    )
