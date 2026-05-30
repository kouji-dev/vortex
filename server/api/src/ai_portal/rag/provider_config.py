"""Deploy-vs-runtime provider config for RAG provider layers.

The *universe* of every external dependency (embedders, vector stores,
rerankers, search providers, connector TYPES) is declared at deploy time in
YAML/env — never editable at runtime. The UI may only:

- enable/disable a declared provider
- pick a per-KB (or default-for-web) default among the **enabled** declared set

It may NOT add a provider, change an endpoint URL, or edit a secret. See the
suite-overview "Deployment Config vs Runtime State" section.

This module is the single source of truth that loads that declared set from
YAML (``rag_providers:`` section of ``config.yaml``) + env overrides, falls
back to a sane bundled default (every backend the code ships), and enforces
"selection-from-set" so KB settings can never reference an undeclared or
disabled provider.

Layer shape (per entry):
    id        — stable provider id (matches the code registry name)
    enabled   — runtime toggle (default True)
    endpoint  — connection URL / base URL (deploy-only; may be None)
    has_credential — whether a secret is configured (never leaks the secret)
    is_default — at most one per layer; the KB/web default

YAML example (``config.yaml``)::

    rag_providers:
      embedders:
        default: voyage-3
        items:
          - id: voyage-3
          - id: text-embedding-3-small
            enabled: false
      vector_stores:
        default: pgvector
        items:
          - id: pgvector
          - id: qdrant
            endpoint: http://qdrant:6333
            credential_env: QDRANT_API_KEY
      rerankers:
        default: voyage-rerank-2
        items:
          - id: voyage-rerank-2
      search_providers:
        default_for_web: tavily
        items:
          - id: tavily
            credential_env: TAVILY_API_KEY
          - id: internal_kbs
      connectors:
        items:
          - id: files
          - id: github
            credential_env: GITHUB_TOKEN

Anything omitted from YAML is filled from the bundled default (all code-level
providers, enabled). When YAML *is* present for a layer, only the listed ids
are "available" — that is how a deployment narrows the universe.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# ── layer keys ───────────────────────────────────────────────────────────

EMBEDDERS = "embedders"
VECTOR_STORES = "vector_stores"
RERANKERS = "rerankers"
SEARCH_PROVIDERS = "search_providers"
CONNECTORS = "connectors"

LAYERS: tuple[str, ...] = (
    EMBEDDERS,
    VECTOR_STORES,
    RERANKERS,
    SEARCH_PROVIDERS,
    CONNECTORS,
)


# ── bundled universe (code-level set; the absolute max any deploy can use) ─
#
# Kept here (not imported from each registry) so this module has no import-time
# dependency on optional SDKs. Each id matches the corresponding registry name.

_BUNDLED_EMBEDDERS: tuple[str, ...] = (
    "voyage-3",
    "voyage-3-lite",
    "text-embedding-3-small",
    "text-embedding-3-large",
)
_BUNDLED_VECTOR_STORES: tuple[str, ...] = (
    "pgvector",
    "qdrant",
    "pinecone",
    "weaviate",
)
_BUNDLED_RERANKERS: tuple[str, ...] = (
    "voyage-rerank-2",
    "cohere-rerank-3.5",
    "bge-reranker-v2-m3",
)
_BUNDLED_SEARCH_PROVIDERS: tuple[str, ...] = (
    "tavily",
    "exa",
    "brave",
    "bing",
    "google_cse",
    "internal_kbs",
)
_BUNDLED_CONNECTORS: tuple[str, ...] = (
    "files",
    "web_crawler",
    "s3",
    "azure_blob",
    "gcs",
    "google_drive",
    "onedrive_sharepoint",
    "confluence",
    "notion",
    "slack",
    "github",
    "gitlab",
    "imap_email",
    "salesforce_kb",
    "zendesk",
    "jira",
    "http_generic",
)

_BUNDLED: dict[str, tuple[str, ...]] = {
    EMBEDDERS: _BUNDLED_EMBEDDERS,
    VECTOR_STORES: _BUNDLED_VECTOR_STORES,
    RERANKERS: _BUNDLED_RERANKERS,
    SEARCH_PROVIDERS: _BUNDLED_SEARCH_PROVIDERS,
    CONNECTORS: _BUNDLED_CONNECTORS,
}

# Per-layer "default" key name (search providers use default_for_web).
_DEFAULT_KEY: dict[str, str] = {
    EMBEDDERS: "default",
    VECTOR_STORES: "default",
    RERANKERS: "default",
    SEARCH_PROVIDERS: "default_for_web",
    CONNECTORS: "default",
}

# Fallback default id per layer when YAML declares none.
_FALLBACK_DEFAULT: dict[str, str | None] = {
    EMBEDDERS: "voyage-3",
    VECTOR_STORES: "pgvector",
    RERANKERS: "voyage-rerank-2",
    SEARCH_PROVIDERS: "tavily",
    CONNECTORS: None,  # connectors have no single default
}


# ── data shapes ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProviderEntry:
    """One declared provider in a layer (deploy-declared, runtime-toggled)."""

    id: str
    enabled: bool = True
    endpoint: str | None = None
    has_credential: bool = False
    is_default: bool = False

    def to_public(self) -> dict[str, Any]:
        """Serialisable view — never includes the secret value itself."""
        return {
            "id": self.id,
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "has_credential": self.has_credential,
            "is_default": self.is_default,
        }


@dataclass(frozen=True)
class LayerConfig:
    """The declared set + default for a single provider layer."""

    layer: str
    items: tuple[ProviderEntry, ...] = ()
    default_id: str | None = None

    def available_ids(self) -> tuple[str, ...]:
        """Every declared id (enabled or not)."""
        return tuple(e.id for e in self.items)

    def enabled_ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.items if e.enabled)

    def get(self, provider_id: str) -> ProviderEntry | None:
        for e in self.items:
            if e.id == provider_id:
                return e
        return None

    def is_selectable(self, provider_id: str) -> bool:
        """True only if declared AND enabled — the rule KB settings enforces."""
        e = self.get(provider_id)
        return e is not None and e.enabled

    def to_public(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "default_id": self.default_id,
            "items": [e.to_public() for e in self.items],
        }


@dataclass(frozen=True)
class ProviderConfig:
    """All RAG provider layers for one deployment."""

    layers: dict[str, LayerConfig] = field(default_factory=dict)

    def layer(self, name: str) -> LayerConfig:
        if name not in self.layers:
            raise KeyError(f"unknown provider layer: {name!r}")
        return self.layers[name]

    def to_public(self) -> dict[str, Any]:
        return {name: lc.to_public() for name, lc in self.layers.items()}


class ProviderNotSelectable(ValueError):
    """Raised when a KB setting references an undeclared/disabled provider."""

    def __init__(self, layer: str, provider_id: str, allowed: tuple[str, ...]):
        self.layer = layer
        self.provider_id = provider_id
        self.allowed = allowed
        super().__init__(
            f"{provider_id!r} is not a selectable {layer} "
            f"(enabled set: {', '.join(allowed) or '∅'})"
        )


# ── loading ──────────────────────────────────────────────────────────────


def _config_path() -> Path:
    env_path = os.environ.get("AI_PORTAL_CONFIG")
    if env_path:
        return Path(env_path)
    # backend/config.yaml — three parents up from this file's package root.
    # this file: .../ai_portal/rag/provider_config.py
    return Path(__file__).resolve().parents[3] / "config.yaml"


def _read_yaml_section(path: Path | None) -> dict[str, Any]:
    p = path or _config_path()
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (yaml.YAMLError, OSError):
        return {}
    section = data.get("rag_providers")
    return section if isinstance(section, dict) else {}


def _env_default(layer: str) -> str | None:
    """Env override for a layer's default, e.g. ``RAG_EMBEDDER_DEFAULT``."""
    key = {
        EMBEDDERS: "RAG_EMBEDDER_DEFAULT",
        VECTOR_STORES: "RAG_VECTOR_STORE_DEFAULT",
        RERANKERS: "RAG_RERANKER_DEFAULT",
        SEARCH_PROVIDERS: "RAG_WEB_SEARCH_DEFAULT",
    }.get(layer)
    if not key:
        return None
    val = os.environ.get(key, "").strip()
    return val or None


def _build_layer(
    layer: str,
    raw: dict[str, Any] | None,
    env: dict[str, str],
) -> LayerConfig:
    bundled = _BUNDLED[layer]
    default_key = _DEFAULT_KEY[layer]

    raw = raw or {}
    raw_items = raw.get("items")

    # When YAML declares items, that narrows the universe to exactly those ids
    # (intersected with the bundled set — an unknown id is dropped, never
    # invented). When absent, the universe is the full bundled set, enabled.
    declared: list[dict[str, Any]]
    if isinstance(raw_items, list) and raw_items:
        declared = [it for it in raw_items if isinstance(it, dict) and it.get("id")]
        declared = [it for it in declared if it["id"] in bundled]
    else:
        declared = [{"id": pid} for pid in bundled]

    # Resolve the default: env > yaml > fallback. Must be among declared ids.
    default_id = (
        _env_default(layer)
        or (raw.get(default_key) if isinstance(raw.get(default_key), str) else None)
        or _FALLBACK_DEFAULT[layer]
    )
    declared_ids = {it["id"] for it in declared}
    if default_id not in declared_ids:
        default_id = next(iter(declared_ids), None) if layer != CONNECTORS else None

    entries: list[ProviderEntry] = []
    for it in declared:
        pid = it["id"]
        enabled = bool(it.get("enabled", True))
        endpoint = it.get("endpoint")
        cred_env = it.get("credential_env")
        has_cred = bool(cred_env and env.get(cred_env, "").strip())
        entries.append(
            ProviderEntry(
                id=pid,
                enabled=enabled,
                endpoint=endpoint if isinstance(endpoint, str) else None,
                has_credential=has_cred,
                is_default=(pid == default_id),
            )
        )

    return LayerConfig(layer=layer, items=tuple(entries), default_id=default_id)


def load_provider_config(
    *,
    path: Path | None = None,
    env: dict[str, str] | None = None,
) -> ProviderConfig:
    """Build the full provider config from YAML + env.

    ``path`` / ``env`` are injectable for tests. Production reads
    ``config.yaml`` (or ``AI_PORTAL_CONFIG``) + ``os.environ``.
    """
    env = dict(os.environ) if env is None else env
    section = _read_yaml_section(path)
    layers = {
        layer: _build_layer(layer, section.get(layer), env) for layer in LAYERS
    }
    return ProviderConfig(layers=layers)


@lru_cache(maxsize=1)
def get_provider_config() -> ProviderConfig:
    """Cached deployment provider config (cleared via :func:`reset_cache`)."""
    return load_provider_config()


def reset_cache() -> None:
    """Drop the cached config (call after editing config in tests/admin)."""
    get_provider_config.cache_clear()


# ── enforcement helpers (used by KB settings validation) ─────────────────


def ensure_selectable(layer: str, provider_id: str, *, cfg: ProviderConfig | None = None) -> str:
    """Return ``provider_id`` if it is a declared+enabled member of ``layer``.

    Raises :class:`ProviderNotSelectable` otherwise. This is the single
    chokepoint KB settings call so the UI can never persist an undeclared or
    disabled provider.
    """
    cfg = cfg or get_provider_config()
    lc = cfg.layer(layer)
    if not lc.is_selectable(provider_id):
        raise ProviderNotSelectable(layer, provider_id, lc.enabled_ids())
    return provider_id


def default_for(layer: str, *, cfg: ProviderConfig | None = None) -> str | None:
    cfg = cfg or get_provider_config()
    return cfg.layer(layer).default_id


__all__ = [
    "CONNECTORS",
    "EMBEDDERS",
    "LAYERS",
    "RERANKERS",
    "SEARCH_PROVIDERS",
    "VECTOR_STORES",
    "LayerConfig",
    "ProviderConfig",
    "ProviderEntry",
    "ProviderNotSelectable",
    "default_for",
    "ensure_selectable",
    "get_provider_config",
    "load_provider_config",
    "reset_cache",
]
