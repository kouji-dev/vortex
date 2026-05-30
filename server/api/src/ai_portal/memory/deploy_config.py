"""Deploy-vs-runtime config for pluggable memory providers.

Principle (suite-wide): the *available SET* of providers is fixed at deploy
time via env/YAML. Runtime callers (UI, KB settings, API requests) may only
*select* a provider that is in the declared set — never free-form.

The registries (extractors / recallers / stores / policies) hold every
bundled implementation. This module narrows that to the operator-declared
subset so an org cannot, e.g., pick ``vector_qdrant`` when the deployment
never provisioned Qdrant.

Declared set comes from env vars (comma-separated), falling back to "all
bundled" when unset so dev / tests keep working with zero config:

    MEMORY_EXTRACTORS=llm_default,llm_typed,rule_based,no_op
    MEMORY_RECALLERS=vector_pgvector,hybrid
    MEMORY_STORES=postgres_default
    MEMORY_POLICIES=default,strict_eu

A declared name that is not registered is dropped (with a warning) so a
typo can never silently enable a non-existent provider. The default
selection per kind is the first declared name, overridable via:

    MEMORY_DEFAULT_EXTRACTOR / _RECALLER / _STORE / _POLICY
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

Kind = str  # "extractor" | "recaller" | "store" | "policy"

_KINDS: tuple[Kind, ...] = ("extractor", "recaller", "store", "policy")

_ENV_SET: dict[Kind, str] = {
    "extractor": "MEMORY_EXTRACTORS",
    "recaller": "MEMORY_RECALLERS",
    "store": "MEMORY_STORES",
    "policy": "MEMORY_POLICIES",
}

_ENV_DEFAULT: dict[Kind, str] = {
    "extractor": "MEMORY_DEFAULT_EXTRACTOR",
    "recaller": "MEMORY_DEFAULT_RECALLER",
    "store": "MEMORY_DEFAULT_STORE",
    "policy": "MEMORY_DEFAULT_POLICY",
}

# Hard fallback default per kind when neither env nor declared-order applies.
_FALLBACK_DEFAULT: dict[Kind, str] = {
    "extractor": "llm_default",
    "recaller": "vector_pgvector",
    "store": "postgres_default",
    "policy": "default",
}


def _registered_names(kind: Kind) -> list[str]:
    """All names currently registered for ``kind`` (the bundled universe)."""
    if kind == "extractor":
        from ai_portal.memory.extractors.registry import list_names
    elif kind == "recaller":
        from ai_portal.memory.recallers.registry import list_names
    elif kind == "store":
        from ai_portal.memory.stores.registry import list_names
    elif kind == "policy":
        from ai_portal.memory.policies.registry import list_names
    else:  # pragma: no cover - guarded by callers
        raise ValueError(f"unknown provider kind: {kind}")
    return list(list_names())


def _parse_env_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


class UnknownProviderKind(ValueError):
    """Raised when an unrecognised provider kind is passed."""


class ProviderNotDeclared(ValueError):
    """Raised when a runtime selection is not in the declared set."""

    def __init__(self, kind: Kind, name: str, declared: list[str]) -> None:
        self.kind = kind
        self.name = name
        self.declared = declared
        super().__init__(
            f"{kind} '{name}' not in declared set {declared}; "
            "deployment must enable it via env first"
        )


def _ensure_kind(kind: Kind) -> None:
    if kind not in _KINDS:
        raise UnknownProviderKind(f"unknown provider kind: {kind!r}")


def list_enabled(kind: Kind, *, env: dict[str, str] | None = None) -> list[str]:
    """Declared (operator-enabled) provider names for ``kind``.

    Intersects the env-declared list with what is actually registered. When
    the env var is unset, returns every registered name (dev / test default).
    Order is preserved from the env declaration; registered-only names keep
    their sorted order.
    """
    _ensure_kind(kind)
    env = os.environ if env is None else env
    registered = _registered_names(kind)
    declared_raw = _parse_env_list(env.get(_ENV_SET[kind]))
    if not declared_raw:
        return registered
    out: list[str] = []
    reg_set = set(registered)
    for name in declared_raw:
        if name in reg_set:
            if name not in out:
                out.append(name)
        else:
            logger.warning(
                "memory.deploy_config.unknown_declared %s=%s (not registered)",
                _ENV_SET[kind],
                name,
            )
    return out


def is_enabled(kind: Kind, name: str, *, env: dict[str, str] | None = None) -> bool:
    return name in list_enabled(kind, env=env)


def default_for(kind: Kind, *, env: dict[str, str] | None = None) -> str:
    """Default selection for ``kind``.

    Priority: explicit ``MEMORY_DEFAULT_*`` env (if enabled) → hard fallback
    (if enabled) → first declared enabled name.
    """
    _ensure_kind(kind)
    env = os.environ if env is None else env
    enabled = list_enabled(kind, env=env)
    explicit = (env.get(_ENV_DEFAULT[kind]) or "").strip()
    if explicit and explicit in enabled:
        return explicit
    if explicit and explicit not in enabled:
        logger.warning(
            "memory.deploy_config.default_not_enabled %s=%s",
            _ENV_DEFAULT[kind],
            explicit,
        )
    fallback = _FALLBACK_DEFAULT.get(kind)
    if fallback and fallback in enabled:
        return fallback
    if enabled:
        return enabled[0]
    # Nothing enabled / registered — return the hard fallback name so callers
    # still get a deterministic value (validation elsewhere will reject use).
    return fallback or ""


def validate_selection(
    kind: Kind, name: str, *, env: dict[str, str] | None = None
) -> str:
    """Return ``name`` if it is in the declared set, else raise.

    Use at the boundary (API request / KB settings save) to reject any
    free-form provider name that the deployment did not enable.
    """
    _ensure_kind(kind)
    if is_enabled(kind, name, env=env):
        return name
    raise ProviderNotDeclared(kind, name, list_enabled(kind, env=env))


@dataclass(slots=True)
class EnabledProviders:
    extractors: list[str]
    recallers: list[str]
    stores: list[str]
    policies: list[str]
    defaults: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "extractors": self.extractors,
            "recallers": self.recallers,
            "stores": self.stores,
            "policies": self.policies,
            "defaults": self.defaults,
        }


def enabled_providers(*, env: dict[str, str] | None = None) -> EnabledProviders:
    """Snapshot of the declared set for every kind + the per-kind defaults.

    Powers the ``GET /v1/memories/providers`` endpoint so the UI can render
    selects populated only with operator-enabled providers.
    """
    return EnabledProviders(
        extractors=list_enabled("extractor", env=env),
        recallers=list_enabled("recaller", env=env),
        stores=list_enabled("store", env=env),
        policies=list_enabled("policy", env=env),
        defaults={
            "extractor": default_for("extractor", env=env),
            "recaller": default_for("recaller", env=env),
            "store": default_for("store", env=env),
            "policy": default_for("policy", env=env),
        },
    )


__all__ = [
    "EnabledProviders",
    "ProviderNotDeclared",
    "UnknownProviderKind",
    "default_for",
    "enabled_providers",
    "is_enabled",
    "list_enabled",
    "validate_selection",
]
