"""SSO HTTP routes — POST /v1/auth/sso/start, GET /v1/auth/sso/callback/{kind}.

Phase G5 of the Control Plane plan.

``POST /v1/auth/sso/start`` resolves an IdP by email domain (or org slug)
and returns a 302 to the IdP's authorize endpoint.

``GET /v1/auth/sso/callback/{kind}`` is the redirect target the IdP posts
the auth code to. We validate the response, JIT-provision the user, mint a
session and return a JSON token bundle. Most deployments will instead
redirect the browser back to the SPA — that shape is delegated to the
front-end via an HTML page wrapper, kept out of the backend.

State is cached in-process; see ``ai_portal.auth.sso`` for details.
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.auth.limiter import sso_callback_limiter
from ai_portal.auth.schemas import TokenResponse
from ai_portal.auth.sessions import create_session
from ai_portal.auth.sso import IdpNotFound, SsoError, complete_sso, start_sso
from ai_portal.auth.strategies.dev import UserManager
from ai_portal.core.config import get_settings

# Self-prefixed at /v1/auth/sso to match the spec; mounted directly on the app.
router = APIRouter(prefix="/v1/auth/sso", tags=["auth", "sso"])


# ── schemas ────────────────────────────────────────────────────────────────


class SsoStartRequest(BaseModel):
    """At least one of ``email`` or ``org_slug`` is required."""

    email: str | None = None
    org_slug: str | None = None
    redirect_uri: str | None = None


# ── helpers ────────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "-"


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _build_redirect_uri(request: Request, kind: str) -> str:
    """Default the IdP redirect_uri to ``<this app>/v1/auth/sso/callback/{kind}``."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/v1/auth/sso/callback/{kind}"


# ── routes ─────────────────────────────────────────────────────────────────


@router.post(
    "/start",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
)
async def sso_start(
    body: SsoStartRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Resolve the IdP and redirect the browser to the authorize endpoint."""
    if not body.email and not body.org_slug:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_lookup", "message": "email or org_slug required"},
        )
    # Need the IdP's ``kind`` to build the default callback URL. Look it up
    # via the same resolver the service uses internally.
    from ai_portal.auth.sso import resolve_idp_for_login

    try:
        conn = resolve_idp_for_login(
            db, email=body.email, org_slug=body.org_slug
        )
    except IdpNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "error": "idp_not_found",
                "message": "no SSO connection matches the supplied hint",
            },
        )
    redirect_uri = body.redirect_uri or _build_redirect_uri(request, conn.kind)
    try:
        result = await start_sso(
            db,
            email=body.email,
            org_slug=body.org_slug,
            redirect_uri=redirect_uri,
        )
    except IdpNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "idp_not_found"},
        )
    except SsoError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "sso_start_failed", "message": str(exc)},
        )
    return RedirectResponse(
        url=result.redirect_url, status_code=status.HTTP_302_FOUND
    )


@router.get("/callback/{kind}", response_model=TokenResponse)
async def sso_callback_get(
    kind: str,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """OIDC-style callback (auth code in query string)."""
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_state"},
        )
    return await _finish_callback(
        kind=kind,
        request=request,
        db=db,
        state=state,
        params=dict(request.query_params),
    )


@router.post("/callback/{kind}", response_model=TokenResponse)
async def sso_callback_post(
    kind: str,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """SAML-style callback (SAMLResponse + RelayState in form body)."""
    form = await request.form()
    params = {k: v for k, v in form.items()}
    state = params.get("RelayState") or params.get("state")
    if not state:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_state"},
        )
    return await _finish_callback(
        kind=kind, request=request, db=db, state=state, params=params
    )


async def _finish_callback(
    *,
    kind: str,
    request: Request,
    db: Session,
    state: str,
    params: dict,
) -> TokenResponse:
    ip = _client_ip(request)
    # Bucket per (ip, kind) — brute-forced state values still get throttled.
    bucket_key = kind or "sso"
    retry_after = sso_callback_limiter.check(ip, bucket_key)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "too_many_sso_callbacks"},
            headers={"Retry-After": str(retry_after)},
        )
    try:
        result = await complete_sso(db, state=state, params=params)
    except SsoError as exc:
        sso_callback_limiter.record_failure(ip, bucket_key)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "sso_callback_failed", "message": str(exc)},
        )
    user = result.user
    sso_callback_limiter.record_success(ip, bucket_key)
    db.commit()  # persist JIT-created user before minting tokens

    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    session_id = _uuid.uuid4()
    tokens = manager.create_tokens(user, session_id=session_id)
    create_session(
        db,
        user_id=user.id,
        session_id=session_id,
        refresh_token=tokens["refresh_token"],
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return TokenResponse(**tokens)
