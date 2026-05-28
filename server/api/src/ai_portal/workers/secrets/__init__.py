"""Worker secrets — bindings, injection, leak detection.

Public surface:

- :class:`SecretRef` — opaque reference to a stored secret value.
- :class:`SecretResolver` / :class:`InMemorySecretResolver` — resolves a
  secret_ref to its plaintext value at injection time.
- :func:`select_secrets_for_run` — picks the secret grants for a given pool
  + repo (per-pool / per-repo binding).
- :func:`inject_env` — merges resolved secrets into a sandbox env dict.
- :func:`scan_for_leaks` — secret-detection on a diff or text blob.
- :func:`audit_grant` — emit audit row on grant (re-export of helper).
"""

from ai_portal.workers.secrets.bindings import (
    SecretBinding,
    SecretRef,
    select_secrets_for_run,
)
from ai_portal.workers.secrets.injection import (
    SecretResolver,
    InMemorySecretResolver,
    inject_env,
)
from ai_portal.workers.secrets.scanner import (
    LeakHit,
    scan_for_leaks,
    scan_diff_for_leaks,
)

__all__ = [
    "SecretRef",
    "SecretBinding",
    "select_secrets_for_run",
    "SecretResolver",
    "InMemorySecretResolver",
    "inject_env",
    "LeakHit",
    "scan_for_leaks",
    "scan_diff_for_leaks",
]
