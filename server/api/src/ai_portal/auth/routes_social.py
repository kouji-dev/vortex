"""Social login routes — GET /v1/auth/social/{provider}/start + /callback.

Consumer OAuth (Google / GitHub / GitLab). Enabled per-deployment via auth
config and gated here: a disabled or unregistered provider returns 404.

``/start`` builds the provider authorize URL, caches state→redirect_uri, and
302s the browser. ``/callback`` exchanges the code, JIT-provisions the user
(personal org for first-time sign-in) and mints a session token bundle.

State cache is in-process (single-worker / tests). Production should back it
with Redis, same as the SSO state cache.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import ai_portal.auth.social.providers  # noqa: F401 — register social providers
from ai_portal.auth.claims_provision import ProvisionError, provision_from_claims
from ai_portal.auth.config import get_auth_config
from ai_portal.auth.deps import get_db
from ai_portal.auth.limiter import sso_callback_limiter
from ai_portal.auth.schemas import TokenResponse
from ai_portal.auth.sessions import create_session
from ai_portal.auth.social.providers._base import SocialOAuthError
from ai_portal.auth.social.registry import (
    SocialProviderNotConfigured,
    SocialProviderNotFound,
    get_social_provider,
)
from ai_portal.auth.strategies.dev import UserManager
from ai_portal.core.config import get_settings

router = APIRouter(prefix="/v1/auth/social", tags=["auth", "social"])


# ── in-process state cache ───────────────────────────────────────────────────


class _SocialStateCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._data: dict[str, tuple[str, str]] = {}

    async def put(self, state: str, provider: str, redirect_uri: str) -> None:
        async with self._lock:
            self._data[state] = (provider, redirect_uri)

    async def pop(self, state: str) -> tuple[str, str] | None:
        async with self._lock:
            return self._data.pop(state, None)

    def clear(self) -> None:
        self._data.clear()


_STATE = _SocialStateCache()


def social_state_cache() -> _SocialStateCache:
    return _STATE


# ── helpers ──────────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "-"


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _callback_uri(request: Request, provider: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/v1/auth/social/{provider}/callback"


def _require_provider_enabled(provider: str):
    cfg = get_auth_config()
    if provider not in cfg.social_providers:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "provider_not_enabled", "provider": provider},
        )
    try:
        return get_social_provider(provider)
    except SocialProviderNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "unknown_provider", "provider": provider},
        )
    except SocialProviderNotConfigured:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "provider_not_configured", "provider": provider},
        )


# ── routes ───────────────────────────────────────────────────────────────────


@router.get(
    "/{provider}/start",
    status_code=status.HTTP_302_FOUND,
    response_class=RedirectResponse,
)
async def social_start(
    provider: str,
    request: Request,
) -> RedirectResponse:
    prov = _require_provider_enabled(provider)
    state = secrets.token_urlsafe(32)
    redirect_uri = _callback_uri(request, provider)
    url = prov.authorize_url(state=state, redirect_uri=redirect_uri)
    await _STATE.put(state, provider, redirect_uri)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/{provider}/callback", response_model=TokenResponse)
async def social_callback(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    prov = _require_provider_enabled(provider)
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"error": "missing_state"}
        )

    ip = _client_ip(request)
    retry_after = sso_callback_limiter.check(ip, f"social:{provider}")
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "too_many_callbacks"},
            headers={"Retry-After": str(retry_after)},
        )

    pending = await _STATE.pop(state)
    if pending is None or pending[0] != provider:
        sso_callback_limiter.record_failure(ip, f"social:{provider}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "unknown_or_expired_state"},
        )
    redirect_uri = pending[1]

    try:
        claims = await prov.exchange(
            params=dict(request.query_params),
            state=state,
            redirect_uri=redirect_uri,
        )
    except SocialOAuthError as exc:
        sso_callback_limiter.record_failure(ip, f"social:{provider}")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "social_exchange_failed", "message": str(exc)},
        )

    try:
        user = provision_from_claims(db, claims=claims)
    except ProvisionError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": "provision_failed", "message": str(exc)},
        )
    db.commit()
    sso_callback_limiter.record_success(ip, f"social:{provider}")

    settings = get_settings()
    manager = UserManager(db=db, secret=settings.secret_key)
    session_id = _uuid.uuid4()
    tokens = manager.create_tokens(user, session_id=session_id)
    create_session(
        db,
        user_id=user.id,
        session_id=session_id,
        refresh_token=tokens["refresh_token"],
        ip=ip,
        user_agent=_user_agent(request),
    )
    return TokenResponse(**tokens)
