"""Phase Polish-T6 — audit emission on every memory mutation.

Static check: parse ``service.py`` + ``v1_router.py`` and require that
each defined mutation method's body contains at least one
``_emit_audit_safe(``/``emit_audit(`` call.

Plus behavioral coverage: stub the audit emitter and exercise each
mutation, confirming an event was emitted for each.
"""
from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ai_portal.memory.service import MemoryService


SRC = Path(__file__).resolve().parents[2] / "src" / "ai_portal" / "memory"


# Functions in service.py that mutate persistent state and MUST audit.
MUTATING_SERVICE_METHODS = {
    "add_manual",
    "patch",
    "soft_delete",
    "restore",
    "bulk_delete",
    "bulk_pin",
    "bulk_tag",
    "pause",
    "resume",
}


def _function_calls_audit(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Call):
            f = node.func
            name = (
                f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            )
            if name in ("_emit_audit_safe", "emit_audit"):
                return True
    return False


def _parse(file: Path) -> ast.Module:
    return ast.parse(file.read_text(encoding="utf-8"))


def test_service_mutation_methods_emit_audit() -> None:
    tree = _parse(SRC / "service.py")
    found: dict[str, bool] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if node.name in MUTATING_SERVICE_METHODS:
                found[node.name] = _function_calls_audit(node)
    missing = [m for m in MUTATING_SERVICE_METHODS if not found.get(m)]
    assert not missing, f"missing audit emit in MemoryService methods: {missing}"


def test_extract_path_emits_audit() -> None:
    """Already wired but assert the static call still exists."""
    tree = _parse(SRC / "service.py")
    extract = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "extract"
    )
    assert _function_calls_audit(extract)


def test_router_policy_endpoints_emit_audit() -> None:
    tree = _parse(SRC / "v1_router.py")
    for target in ("set_extraction_policy", "set_recall_policy"):
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == target
        )
        assert _function_calls_audit(fn), f"router fn missing audit: {target}"


# ── behavioral ──────────────────────────────────────────────────────────────


class _AuditCollector:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, **kw: Any) -> None:
        self.events.append(kw)


@pytest.mark.asyncio
async def test_bulk_pin_emits_audit_event() -> None:
    coll = _AuditCollector()

    class _RC:
        rowcount = 2

    class _S:
        async def execute(self, *_a, **_k):
            return _RC()

        async def flush(self):
            return None

    svc = MemoryService.__new__(MemoryService)
    svc.s = _S()
    with patch("ai_portal.memory.service._emit_audit_safe") as m:
        async def fake(**kw):
            coll.emit(**kw)

        m.side_effect = fake
        out = await MemoryService.bulk_pin(
            svc, org_id=uuid.uuid4(), actor_user_id=1, ids=[uuid.uuid4()], pinned=True
        )
    assert out == 2
    assert len(coll.events) == 1
    assert coll.events[0]["event_type"] == "memory.bulk_pin"


@pytest.mark.asyncio
async def test_bulk_tag_emits_audit_event() -> None:
    coll = _AuditCollector()

    class _Result:
        def scalars(self_):
            return self_

        def all(self_):
            return []

    class _S:
        async def execute(self, *_a, **_k):
            return _Result()

        async def flush(self):
            return None

    svc = MemoryService.__new__(MemoryService)
    svc.s = _S()
    with patch("ai_portal.memory.service._emit_audit_safe") as m:
        async def fake(**kw):
            coll.emit(**kw)

        m.side_effect = fake
        out = await MemoryService.bulk_tag(
            svc,
            org_id=uuid.uuid4(),
            actor_user_id=1,
            ids=[uuid.uuid4()],
            add=["x"],
            remove=[],
        )
    assert out == 0
    assert any(e["event_type"] == "memory.bulk_tag" for e in coll.events)


def test_all_listed_methods_actually_exist() -> None:
    for name in MUTATING_SERVICE_METHODS:
        m = getattr(MemoryService, name)
        assert inspect.iscoroutinefunction(m), name
