"""Validate commit subject against Conventional Commits.

Subject grammar::

    <type>[optional scope][!]: <description>

Where ``type`` is one of ``DEFAULT_TYPES`` (configurable per pool) and
description is non-empty and short. Pool settings control whether the
check is enforced (``settings.commits.enforce_conventional = true``).

Used by the verify step before allowing a commit. Agent loops surface
the error so the model can retry with a compliant message.
"""

from __future__ import annotations

import re

DEFAULT_TYPES: tuple[str, ...] = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)

_MAX_SUBJECT_LEN = 100

# <type>(scope)!: subject
_SUBJECT_RE = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[a-z0-9_\-./]+)\))?"
    r"(?P<breaking>!)?"
    r": (?P<subject>.+)$"
)


class ConventionalCommitError(ValueError):
    """Raised when a commit subject violates the convention."""


def validate_commit_message(
    message: str,
    *,
    allowed_types: tuple[str, ...] = DEFAULT_TYPES,
    max_subject_len: int = _MAX_SUBJECT_LEN,
) -> None:
    """Raise :class:`ConventionalCommitError` on bad subject."""
    if not message or not message.strip():
        raise ConventionalCommitError("commit message is empty")

    subject = message.splitlines()[0].rstrip()
    if len(subject) > max_subject_len:
        raise ConventionalCommitError(
            f"subject longer than {max_subject_len} chars"
        )

    m = _SUBJECT_RE.match(subject)
    if not m:
        raise ConventionalCommitError(
            f"subject does not match <type>(scope)?!?: <desc>: {subject!r}"
        )

    ctype = m.group("type")
    if ctype not in allowed_types:
        raise ConventionalCommitError(
            f"unknown commit type {ctype!r}; allowed={allowed_types}"
        )

    desc = m.group("subject").strip()
    if not desc:
        raise ConventionalCommitError("description is empty")
