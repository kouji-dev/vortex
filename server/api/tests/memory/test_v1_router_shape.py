"""Phase J — v1 router endpoint registration."""
from __future__ import annotations

from ai_portal.memory.v1_router import router


def _routes() -> set[str]:
    return {r.path for r in router.routes}


def test_router_has_expected_endpoints() -> None:
    paths = _routes()
    expected = {
        "/v1/memories",
        "/v1/memories/{memory_id}",
        "/v1/memories/bulk-delete",
        "/v1/memories/extract",
        "/v1/memories/recall",
        "/v1/memories/{memory_id}/uses",
        "/v1/memories/policies",
        "/v1/memories/policies/extraction",
        "/v1/memories/policies/recall",
        "/v1/memories/pause",
        "/v1/memories/resume",
        "/v1/memories/export",
        "/v1/memories/analytics",
    }
    assert expected <= paths, expected - paths


def test_router_prefix_and_tags() -> None:
    assert router.prefix == "/v1/memories"
    assert "memories-v1" in router.tags
