"""CSRF middleware — double-submit cookie pattern.

Threat model:
- Routes authenticated via cookie sessions are vulnerable to cross-site form
  POSTs because the browser sends cookies automatically.
- Routes authenticated via ``Authorization: Bearer ...`` (API keys, JWT in
  header) are not vulnerable — the browser will not attach the header on a
  cross-origin POST initiated by attacker markup.

Contract:
- Safe methods (GET/HEAD/OPTIONS/TRACE) pass through.
- Requests bearing ``Authorization: Bearer …`` bypass — they are not cookie
  auth, so CSRF does not apply.
- Requests without any session cookie pass through — there is no session to
  forge.
- Requests with a session cookie AND an unsafe method must echo the
  ``csrf_token`` cookie in the ``X-CSRF-Token`` header (or ``_csrf`` form/JSON
  field). Mismatch → 403.

The CSRF cookie itself is minted by ``ensure_csrf_cookie`` (called from any
GET handler that hands back HTML / a login page) — but the middleware does not
require the cookie to be present. If absent, nothing to forge, request passes.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "_csrf"
SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Cookie names commonly used to carry a session — if any is present, CSRF must
# be enforced. Keep this list tight to avoid false positives.
SESSION_COOKIE_NAMES: frozenset[str] = frozenset(
    {"session", "session_id", "sid", "access_token", "refresh_token"}
)


def _new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_csrf_cookie(response: Response, *, existing: str | None = None) -> str:
    """Attach a CSRF cookie if not already present. Returns the token."""
    token = existing or _new_csrf_token()
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        httponly=False,  # JS must read it to echo via header
        secure=True,
        samesite="lax",
        path="/",
    )
    return token


def _has_session_cookie(cookies: dict[str, str]) -> bool:
    return any(name in cookies for name in SESSION_COOKIE_NAMES)


def _has_bearer_auth(headers) -> bool:
    auth = headers.get("authorization") or headers.get("Authorization")
    if not auth:
        return False
    return auth.lower().startswith("bearer ")


async def _submitted_token(request: Request) -> str | None:
    """Resolve the submitted CSRF token from header, then form/JSON body."""
    hdr = request.headers.get(CSRF_HEADER_NAME)
    if hdr:
        return hdr
    ctype = (request.headers.get("content-type") or "").lower()
    if ctype.startswith("application/x-www-form-urlencoded") or ctype.startswith(
        "multipart/form-data"
    ):
        form = await request.form()
        val = form.get(CSRF_FORM_FIELD)
        if isinstance(val, str):
            return val
    if ctype.startswith("application/json"):
        try:
            payload = await request.json()
        except Exception:
            return None
        if isinstance(payload, dict):
            val = payload.get(CSRF_FORM_FIELD)
            if isinstance(val, str):
                return val
    return None


class CsrfMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection.

    Mounts in front of the application routing. Behaviour:
    - safe methods → pass
    - bearer-auth → pass (header-only auth, not CSRF-exposed)
    - no session cookie → pass (no session to forge)
    - otherwise → require X-CSRF-Token header (or _csrf body field) to equal
      the ``csrf_token`` cookie. 403 on mismatch.
    """

    def __init__(self, app, *, exempt_paths: Iterable[str] = ()) -> None:
        super().__init__(app)
        self._exempt = tuple(exempt_paths)

    def _is_exempt(self, path: str) -> bool:
        return any(path == p or path.startswith(p.rstrip("/") + "/") for p in self._exempt)

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in SAFE_METHODS:
            return await call_next(request)
        if self._is_exempt(request.url.path):
            return await call_next(request)
        if _has_bearer_auth(request.headers):
            return await call_next(request)
        cookies = dict(request.cookies)
        if not _has_session_cookie(cookies):
            return await call_next(request)

        cookie_token = cookies.get(CSRF_COOKIE_NAME)
        if not cookie_token:
            return JSONResponse(
                status_code=403,
                content={"detail": "csrf_cookie_missing"},
            )
        submitted = await _submitted_token(request)
        if not submitted or not secrets.compare_digest(cookie_token, submitted):
            return JSONResponse(
                status_code=403,
                content={"detail": "csrf_token_mismatch"},
            )
        return await call_next(request)
