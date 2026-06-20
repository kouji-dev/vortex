"""Control-plane smoke test — end-to-end golden path.

Documents the minimum-viable signup → login → me → api-key → audit flow that
must work against a freshly migrated control-plane DB. Skipped unless
``SMOKE_BACKEND_URL`` env var is set pointing at a live backend booted with:

    DEPLOYMENT_MODE=saas
    SECRET_KEY=<32+ chars>
    AUDIT_KEK=<fernet base64>
    MEMORY_KEK=<fernet base64>
    DATABASE_URL=<freshly migrated DB>

Run:

    SMOKE_BACKEND_URL=http://127.0.0.1:8003 \
        pytest server/api/tests/test_smoke_control_plane.py -v
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest


SMOKE_BACKEND_URL = os.environ.get("SMOKE_BACKEND_URL")

pytestmark = pytest.mark.skipif(
    not SMOKE_BACKEND_URL,
    reason="set SMOKE_BACKEND_URL to a live backend to run the smoke test",
)


@pytest.fixture(scope="module")
def base_url() -> str:
    return SMOKE_BACKEND_URL.rstrip("/")


@pytest.fixture(scope="module")
def credentials() -> dict[str, str]:
    # Unique per run so reruns against the same DB do not collide on email.
    suffix = uuid.uuid4().hex[:8]
    return {
        "email": f"smoke-{suffix}@example.com",
        "password": "StrongPass123!",
    }


def _wait_for_backend(url: str, *, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=2.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    pytest.fail(f"backend not reachable at {url}")


def test_golden_path(base_url: str, credentials: dict[str, str]) -> None:
    """Signup → login → /auth/me → mint key → list audit events."""
    _wait_for_backend(base_url)

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        # 1. Signup — fresh user, fresh org auto-created with role=owner.
        r = client.post("/auth/register", json=credentials)
        assert r.status_code == 201, r.text
        register_body = r.json()
        assert "access_token" in register_body

        # 2. Login — exchange creds for fresh tokens.
        r = client.post("/auth/login", json=credentials)
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        assert token

        auth_headers = {"Authorization": f"Bearer {token}"}

        # 3. /auth/me — token resolves to the user we just created.
        r = client.get("/auth/me", headers=auth_headers)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["email"] == credentials["email"]
        assert me["role"] == "owner"
        assert me["org_id"]

        # 4. Mint a portal API key.
        r = client.post(
            "/api/me/portal-api-keys",
            headers=auth_headers,
            json={"label": "smoke-test"},
        )
        assert r.status_code == 201, r.text
        key = r.json()
        assert key["token"].startswith("aip_")
        assert key["key_prefix"]

        # 5. Audit log — owner can list and sees the events we just emitted.
        r = client.get("/api/admin/audit", headers=auth_headers)
        assert r.status_code == 200, r.text
        audit = r.json()
        assert audit["total"] >= 2, audit
        event_types = {e["event_type"] for e in audit["items"]}
        assert "auth.user.registered" in event_types
        assert "auth.portal_api_key.created" in event_types
