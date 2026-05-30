"""File-scoped unit tests for ``memory.deploy_config``.

These tests exercise the deploy-vs-runtime selection logic in isolation.
``_registered_names`` is monkeypatched so we never trigger the registries'
eager provider imports (which pull in the gateway facade).

The module is loaded directly from its file path so importing it does not
trigger ``ai_portal.memory.__init__`` (which eagerly registers bundled
providers and would pull heavy cross-module deps).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "ai_portal"
    / "memory"
    / "deploy_config.py"
)
_MOD_NAME = "memory_deploy_config_uut"
_spec = importlib.util.spec_from_file_location(_MOD_NAME, _MODULE_PATH)
assert _spec and _spec.loader
dc = importlib.util.module_from_spec(_spec)
# Register before exec so @dataclass(slots=True) introspection can resolve
# the module via sys.modules[cls.__module__].
sys.modules[_MOD_NAME] = dc
_spec.loader.exec_module(dc)


# Fixed "registered universe" used across tests, mirroring the bundled set.
_REGISTERED = {
    "extractor": ["llm_default", "llm_typed", "no_op", "rule_based"],
    "recaller": ["hybrid", "vector_pgvector", "vector_qdrant"],
    "store": ["postgres_default", "rag_backed"],
    "policy": ["default", "strict_eu"],
}


@pytest.fixture(autouse=True)
def _patch_registry(monkeypatch):
    monkeypatch.setattr(
        dc, "_registered_names", lambda kind: list(_REGISTERED[kind])
    )


# ── list_enabled ──────────────────────────────────────────────────────────


def test_unset_env_returns_all_registered():
    for kind, names in _REGISTERED.items():
        assert dc.list_enabled(kind, env={}) == names


def test_declared_subset_filters_and_preserves_order():
    env = {"MEMORY_RECALLERS": "vector_pgvector,hybrid"}
    assert dc.list_enabled("recaller", env=env) == ["vector_pgvector", "hybrid"]


def test_declared_unknown_name_is_dropped():
    env = {"MEMORY_EXTRACTORS": "llm_default,does_not_exist,no_op"}
    assert dc.list_enabled("extractor", env=env) == ["llm_default", "no_op"]


def test_declared_dedupes():
    env = {"MEMORY_POLICIES": "default,default,strict_eu"}
    assert dc.list_enabled("policy", env=env) == ["default", "strict_eu"]


def test_whitespace_and_empty_tokens_ignored():
    env = {"MEMORY_STORES": " postgres_default , , rag_backed "}
    assert dc.list_enabled("store", env=env) == ["postgres_default", "rag_backed"]


def test_unknown_kind_raises():
    with pytest.raises(dc.UnknownProviderKind):
        dc.list_enabled("bogus", env={})


# ── is_enabled ────────────────────────────────────────────────────────────


def test_is_enabled_true_for_declared():
    env = {"MEMORY_RECALLERS": "vector_pgvector"}
    assert dc.is_enabled("recaller", "vector_pgvector", env=env) is True


def test_is_enabled_false_for_undeclared():
    env = {"MEMORY_RECALLERS": "vector_pgvector"}
    assert dc.is_enabled("recaller", "vector_qdrant", env=env) is False


# ── default_for ───────────────────────────────────────────────────────────


def test_default_prefers_hard_fallback_when_enabled():
    # unset env → all enabled → hard fallback wins
    assert dc.default_for("extractor", env={}) == "llm_default"
    assert dc.default_for("recaller", env={}) == "vector_pgvector"
    assert dc.default_for("store", env={}) == "postgres_default"
    assert dc.default_for("policy", env={}) == "default"


def test_explicit_default_env_wins_when_enabled():
    env = {
        "MEMORY_EXTRACTORS": "llm_default,llm_typed",
        "MEMORY_DEFAULT_EXTRACTOR": "llm_typed",
    }
    assert dc.default_for("extractor", env=env) == "llm_typed"


def test_explicit_default_ignored_when_not_enabled():
    env = {
        "MEMORY_EXTRACTORS": "llm_default",  # llm_typed NOT enabled
        "MEMORY_DEFAULT_EXTRACTOR": "llm_typed",
    }
    # falls back to the hard fallback (llm_default), which is enabled
    assert dc.default_for("extractor", env=env) == "llm_default"


def test_default_falls_to_first_enabled_when_fallback_not_enabled():
    env = {"MEMORY_RECALLERS": "hybrid,vector_qdrant"}  # no vector_pgvector
    assert dc.default_for("recaller", env=env) == "hybrid"


# ── validate_selection ────────────────────────────────────────────────────


def test_validate_selection_returns_name_when_enabled():
    env = {"MEMORY_RECALLERS": "vector_pgvector,hybrid"}
    assert dc.validate_selection("recaller", "hybrid", env=env) == "hybrid"


def test_validate_selection_raises_when_not_declared():
    env = {"MEMORY_RECALLERS": "vector_pgvector"}
    with pytest.raises(dc.ProviderNotDeclared) as ei:
        dc.validate_selection("recaller", "vector_qdrant", env=env)
    assert ei.value.kind == "recaller"
    assert ei.value.name == "vector_qdrant"
    assert ei.value.declared == ["vector_pgvector"]


# ── enabled_providers snapshot ────────────────────────────────────────────


def test_enabled_providers_snapshot_shape():
    env = {
        "MEMORY_EXTRACTORS": "llm_default,llm_typed",
        "MEMORY_RECALLERS": "vector_pgvector",
        "MEMORY_STORES": "postgres_default",
        "MEMORY_POLICIES": "default,strict_eu",
    }
    snap = dc.enabled_providers(env=env)
    d = snap.as_dict()
    assert d["extractors"] == ["llm_default", "llm_typed"]
    assert d["recallers"] == ["vector_pgvector"]
    assert d["stores"] == ["postgres_default"]
    assert d["policies"] == ["default", "strict_eu"]
    assert d["defaults"] == {
        "extractor": "llm_default",
        "recaller": "vector_pgvector",
        "store": "postgres_default",
        "policy": "default",
    }
