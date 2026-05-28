"""Router shape — every endpoint mounts as expected.

This test does not exercise auth or DB. It just imports the router and
asserts each expected ``(method, path)`` pair is present, catching typos
and merge regressions cheaply.
"""
from __future__ import annotations

from ai_portal.rag.management.router import router

EXPECTED = {
    ("GET", "/api/kbs/{kb_id}/evals"),
    ("POST", "/api/kbs/{kb_id}/evals"),
    ("GET", "/api/kbs/{kb_id}/evals/{eval_id}"),
    ("PATCH", "/api/kbs/{kb_id}/evals/{eval_id}"),
    ("DELETE", "/api/kbs/{kb_id}/evals/{eval_id}"),
    ("POST", "/api/kbs/{kb_id}/evals/{eval_id}/run"),
    ("GET", "/api/kbs/{kb_id}/evals/{eval_id}/runs"),
    ("POST", "/api/kbs/{kb_id}/playground"),
    ("GET", "/api/kbs/{kb_id}/playground/sessions"),
    ("GET", "/api/kbs/{kb_id}/playground/sessions/{session_id}"),
    ("DELETE", "/api/kbs/{kb_id}/playground/sessions/{session_id}"),
    ("GET", "/api/kbs/{kb_id}/analytics"),
    ("POST", "/api/kbs/{kb_id}/feedback"),
}


def test_router_exposes_all_endpoints() -> None:
    seen: set[tuple[str, str]] = set()
    for r in router.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", set()) or set()
        for m in methods:
            if path:
                seen.add((m, path))
    missing = EXPECTED - seen
    assert not missing, f"missing routes: {missing}"
