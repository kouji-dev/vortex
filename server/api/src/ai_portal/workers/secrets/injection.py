"""Resolve SecretRefs and inject them as env vars in a sandbox.

The injection layer never logs or returns plaintext values directly. The
``inject_env`` helper returns a *new* dict that the sandbox provider passes
to ``provision()``. Plaintext stays in process memory and is never written
to events / audit / artifacts.

Env var name policy:
- ref ``aws/staging/access_key`` → ``AWS_STAGING_ACCESS_KEY``
- ref ``my secret`` → ``MY_SECRET``
- Caller may override per-ref via ``env_name_overrides``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

from ai_portal.workers.secrets.bindings import SecretRef


class SecretNotFound(Exception):
    """The resolver could not find a plaintext value for this ref."""

    def __init__(self, ref: str) -> None:
        super().__init__(f"secret not found: {ref}")
        self.ref = ref


@runtime_checkable
class SecretResolver(Protocol):
    """Anything that maps a ``secret_ref`` to a plaintext value."""

    async def resolve(self, ref: str) -> str: ...


@dataclass
class InMemorySecretResolver:
    """Test/dev resolver — holds plaintexts in a dict."""

    values: dict[str, str] = field(default_factory=dict)

    async def resolve(self, ref: str) -> str:
        if ref not in self.values:
            raise SecretNotFound(ref)
        return self.values[ref]


_SAFE = re.compile(r"[^A-Z0-9_]+")


def _env_name(ref: str) -> str:
    upper = ref.upper().replace("/", "_").replace("-", "_").replace(" ", "_")
    return _SAFE.sub("_", upper).strip("_") or "SECRET"


async def inject_env(
    base_env: dict[str, str],
    *,
    refs: Iterable[SecretRef],
    resolver: SecretResolver,
    env_name_overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return ``base_env`` merged with resolved secrets.

    - Secrets *override* base_env entries with the same key (per-pool
      bindings are authoritative for env names they own).
    - Plaintext values are never copied into the input dicts; we build a
      fresh dict.
    """
    overrides = env_name_overrides or {}
    merged: dict[str, str] = dict(base_env)
    for r in refs:
        name = overrides.get(r.ref) or _env_name(r.ref)
        plaintext = await resolver.resolve(r.ref)
        merged[name] = plaintext
    return merged
