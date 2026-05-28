"""CSRF middleware — double-submit cookie tests.

File-scoped: no DB, no real app. Builds a tiny FastAPI app per scenario and
asserts the middleware decision (pass / 403) under each set of inputs.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.middleware.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CsrfMiddleware,
)


def _build_app(**mw_kwargs) -> FastAPI:
    app = FastAPI()
    app.add_middleware(CsrfMiddleware, **mw_kwargs)

    @app.get("/g")
    def g():
        return {"ok": True}

    @app.post("/p")
    def p():
        return {"ok": True}

    @app.post("/json")
    def j(payload: dict):  # noqa: ARG001
        return {"ok": True}

    return app


# ── safe methods always pass ──────────────────────────────────────────────────


def test_get_passes_without_token():
    c = TestClient(_build_app())
    assert c.get("/g").status_code == 200


# ── bearer auth bypass ────────────────────────────────────────────────────────


def test_bearer_auth_bypasses_csrf():
    c = TestClient(_build_app())
    r = c.post(
        "/p",
        cookies={"session": "abc"},  # session cookie present
        headers={"Authorization": "Bearer xyz"},
    )
    assert r.status_code == 200


# ── no session cookie → pass ──────────────────────────────────────────────────


def test_no_session_cookie_passes():
    c = TestClient(_build_app())
    r = c.post("/p")
    assert r.status_code == 200


# ── session cookie + no CSRF token → 403 ──────────────────────────────────────


def test_cookie_request_without_csrf_token_blocked():
    c = TestClient(_build_app())
    r = c.post("/p", cookies={"session": "abc"})
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_cookie_missing"


def test_cookie_request_with_cookie_but_no_header_blocked():
    c = TestClient(_build_app())
    r = c.post(
        "/p",
        cookies={"session": "abc", CSRF_COOKIE_NAME: "tok-123"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "csrf_token_mismatch"


def test_cookie_request_with_mismatched_header_blocked():
    c = TestClient(_build_app())
    r = c.post(
        "/p",
        cookies={"session": "abc", CSRF_COOKIE_NAME: "tok-123"},
        headers={CSRF_HEADER_NAME: "wrong"},
    )
    assert r.status_code == 403


# ── valid double-submit passes ────────────────────────────────────────────────


def test_matching_double_submit_passes():
    c = TestClient(_build_app())
    r = c.post(
        "/p",
        cookies={"session": "abc", CSRF_COOKIE_NAME: "tok-xyz"},
        headers={CSRF_HEADER_NAME: "tok-xyz"},
    )
    assert r.status_code == 200


def test_json_body_csrf_field_accepted():
    c = TestClient(_build_app())
    r = c.post(
        "/json",
        cookies={"session": "abc", CSRF_COOKIE_NAME: "tok-xyz"},
        json={"_csrf": "tok-xyz", "data": 1},
    )
    assert r.status_code == 200


# ── exempt paths ──────────────────────────────────────────────────────────────


def test_exempt_path_bypasses():
    c = TestClient(_build_app(exempt_paths=("/p",)))
    r = c.post("/p", cookies={"session": "abc"})
    assert r.status_code == 200


# ── other unsafe methods enforced ─────────────────────────────────────────────


def test_put_delete_also_enforced():
    app = FastAPI()
    app.add_middleware(CsrfMiddleware)

    @app.put("/u")
    def u():
        return {"ok": True}

    @app.delete("/d")
    def d():
        return {"ok": True}

    c = TestClient(app)
    assert (
        c.put("/u", cookies={"session": "abc", CSRF_COOKIE_NAME: "t"}).status_code
        == 403
    )
    assert (
        c.delete("/d", cookies={"session": "abc", CSRF_COOKIE_NAME: "t"}).status_code
        == 403
    )
    # Match → pass.
    assert (
        c.put(
            "/u",
            cookies={"session": "abc", CSRF_COOKIE_NAME: "t"},
            headers={CSRF_HEADER_NAME: "t"},
        ).status_code
        == 200
    )
