"""Worker audit hooks — hash + record every shell/file/PR/approval action.

Public surface:

- :func:`audit_shell` — emit ``workers.shell.exec`` audit with stdout/stderr hash.
- :func:`audit_file_write` — emit ``workers.file.write`` with before/after hash.
- :func:`audit_pr_created` — emit ``workers.pr.created`` with diff hash + url.
- :func:`audit_approval_decided` — emit ``workers.approval.decided``.

Each helper computes a SHA-256 hash of the relevant blob and bounds the
payload size so audit rows stay small.
"""

from ai_portal.workers.audit_hooks.hashing import (
    sha256_hex,
    excerpt,
)
from ai_portal.workers.audit_hooks.hooks import (
    audit_shell,
    audit_file_write,
    audit_pr_created,
    audit_approval_decided,
)

__all__ = [
    "sha256_hex",
    "excerpt",
    "audit_shell",
    "audit_file_write",
    "audit_pr_created",
    "audit_approval_decided",
]
