"""Per-pool / per-repo secret bindings.

Each ``WorkerSecretGrant`` row links a ``secret_ref`` to a pool plus an
allow-list of repos. A run only sees the grants whose allow-list either
contains the run's repo or is empty (empty = applies to all repos in the
pool).

This file is pure data shaping — DB / audit happen in higher layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SecretRef:
    """Opaque reference to a stored secret. The value is fetched lazily."""

    ref: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.ref


@dataclass(frozen=True)
class SecretBinding:
    """One row from ``worker_secrets_grants`` reduced to scope inputs.

    ``allow_repos`` empty = pool-wide. Otherwise must match the run repo.
    """

    secret_ref: str
    allow_repos: tuple[str, ...] = ()

    def applies_to(self, repo: str | None) -> bool:
        if not self.allow_repos:
            return True
        return repo is not None and repo in self.allow_repos


def select_secrets_for_run(
    bindings: Iterable[SecretBinding], *, repo: str | None
) -> list[SecretRef]:
    """Filter bindings to the ones that apply to ``repo``.

    Returns SecretRefs in deterministic order (input order) so env injection
    is reproducible.
    """
    out: list[SecretRef] = []
    seen: set[str] = set()
    for b in bindings:
        if not b.applies_to(repo):
            continue
        if b.secret_ref in seen:
            continue
        seen.add(b.secret_ref)
        out.append(SecretRef(ref=b.secret_ref))
    return out
