"""Phase O — public facade exports.

Cross-module callers (chat, assistants, workers, RAG) must be able to
reach everything via ``ai_portal.memory``.
"""
from __future__ import annotations

import ai_portal.memory as M


def test_facade_exposes_service() -> None:
    assert hasattr(M, "MemoryService")
    assert hasattr(M, "ExtractResult")


def test_facade_exposes_registries() -> None:
    for name in (
        "get_extractor",
        "get_recaller",
        "get_store",
        "get_policy",
        "register_extractor",
        "register_recaller",
        "register_store",
        "register_policy",
    ):
        assert callable(getattr(M, name)), name


def test_facade_exposes_schemas() -> None:
    for name in (
        "MemoryOut",
        "MemoryCreate",
        "MemoryPatch",
        "RecallRequest",
        "RecallResult",
        "ExtractRequest",
        "BulkDeleteRequest",
        "ExtractionPolicyDTO",
        "RecallPolicyDTO",
        "PauseRequest",
    ):
        assert hasattr(M, name), name


def test_facade_exposes_integrations_and_rag_tool() -> None:
    assert M.integrations is not None
    assert M.rag_tool.TOOL_DEFINITION["name"] == "memory.search"


def test_bundled_extractors_registered_via_facade() -> None:
    names = set(M.list_extractors())
    assert {"no_op", "rule_based", "llm_default", "llm_typed"} <= names


def test_bundled_policies_registered_via_facade() -> None:
    names = set(M.list_policies())
    assert {"default", "strict_eu"} <= names
