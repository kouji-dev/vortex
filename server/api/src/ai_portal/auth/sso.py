"""SSO orchestration — IdP resolution, JIT user provisioning, session mint.

Phase G5 of the Control Plane plan.

Routes call :func:`start_sso` to resolve the IdP for an incoming login attempt
(by email domain or org slug), persist the cached :class:`OidcProvider`/SAML
instance keyed by ``state``, and redirect to the IdP. The callback calls
:func:`complete_sso` to validate the response, JIT-provision the user the
first time, and create a :class:`UserSession`.

State is held in-process: enough for single-worker deployments and tests; a
production deploy should swap ``_STATE_CACHE`` with Redis-backed storage.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import uuid as _uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.idp.model import IdpConnection
from ai_portal.auth.idp.protocol import IdentityProvider, UserClaims
from ai_portal.auth.idp.registry import get_provider
from ai_portal.auth.model import Org, User


class SsoError(Exception):
    """Generic SSO failure (no IdP found, state expired, JIT failure)."""


class IdpNotFound(SsoError):
    """No enabled IdP connection matches the lookup hint."""


@dataclass(frozen=True, slots=True)
class StartResult:
    """Return value of :func:`start_sso` — the redirect URL + opaque state."""

    redirect_url: str
    state: str
    connection_id: _uuid.UUID


@dataclass(frozen=True, slots=True)
class CompleteResult:
    """Return value of :func:`complete_sso` — the persisted user + claims."""

    user: User
    claims: UserClaims
    connection: IdpConnection


# ── State store ────────────────────────────────────────────────────────────


@dataclass
class _PendingFlow:
    connection_id: _uuid.UUID
    kind: str
    redirect_uri: str
    provider: IdentityProvider


class _StateCache:
    """In-process state cache for pending SSO flows.

    Production deploys swap this with Redis. Keep the surface tiny.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._data: dict[str, _PendingFlow] = {}

    async def put(self, state: str, pending: _PendingFlow) -> None:
        async with self._lock:
            self._data[state] = pending

    async def pop(self, state: str) -> _PendingFlow | None:
        async with self._lock:
            return self._data.pop(state, None)

    def clear(self) -> None:
        """Test helper — wipe the cache between scenarios."""
        self._data.clear()


_STATE_CACHE = _StateCache()


def state_cache() -> _StateCache:
    """Public accessor (tests + routes) for the process-wide state cache."""
    return _STATE_CACHE


# ── IdP resolution ─────────────────────────────────────────────────────────


def _email_domain(email: str) -> str | None:
    """Return the lowercase domain part of an email, or None if malformed."""
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].strip().lower() or None


def resolve_idp_by_domain(
    db: Session, *, domain: str
) -> IdpConnection | None:
    """Return the first enabled IdP connection bound to ``domain``."""
    if not domain:
        return None
    return db.scalars(
        select(IdpConnection)
        .where(
            IdpConnection.domain == domain.lower(),
            IdpConnection.enabled.is_(True),
        )
        .order_by(IdpConnection.created_at.asc())
    ).first()


def resolve_idp_by_org_slug(
    db: Session, *, org_slug: str
) -> IdpConnection | None:
    """Return the first enabled IdP connection on the org with ``org_slug``."""
    org = db.scalars(select(Org).where(Org.slug == org_slug)).first()
    if org is None:
        return None
    return db.scalars(
        select(IdpConnection)
        .where(
            IdpConnection.org_id == org.id,
            IdpConnection.enabled.is_(True),
        )
        .order_by(IdpConnection.created_at.asc())
    ).first()


def resolve_idp_for_login(
    db: Session,
    *,
    email: str | None = None,
    org_slug: str | None = None,
) -> IdpConnection:
    """Locate an IdP for a fresh SSO start request.

    Lookup order: email domain → org slug. Raises :class:`IdpNotFound` if
    neither matches an enabled connection.
    """
    if email:
        domain = _email_domain(email)
        if domain:
            conn = resolve_idp_by_domain(db, domain=domain)
            if conn is not None:
                return conn
    if org_slug:
        conn = resolve_idp_by_org_slug(db, org_slug=org_slug)
        if conn is not None:
            return conn
    raise IdpNotFound("no IdP connection matches email domain or org slug")


# ── Provider instantiation ────────────────────────────────────────────────


def build_provider(conn: IdpConnection) -> IdentityProvider:
    """Decode ``conn.config_encrypted`` and instantiate the provider."""
    try:
        config = json.loads(conn.config_encrypted) if conn.config_encrypted else {}
    except json.JSONDecodeError as exc:
        raise SsoError(f"idp connection {conn.id} has invalid config JSON") from exc
    return get_provider(conn.kind, config)


# ── start / complete ───────────────────────────────────────────────────────


async def start_sso(
    db: Session,
    *,
    email: str | None,
    org_slug: str | None,
    redirect_uri: str,
) -> StartResult:
    """Resolve the IdP, persist pending state, return the redirect URL."""
    conn = resolve_idp_for_login(db, email=email, org_slug=org_slug)
    provider = build_provider(conn)
    state = secrets.token_urlsafe(32)
    url = await provider.initiate(state=state, redirect_uri=redirect_uri)
    await _STATE_CACHE.put(
        state,
        _PendingFlow(
            connection_id=conn.id,
            kind=conn.kind,
            redirect_uri=redirect_uri,
            provider=provider,
        ),
    )
    return StartResult(
        redirect_url=url, state=state, connection_id=conn.id
    )


async def complete_sso(
    db: Session,
    *,
    state: str,
    params: dict[str, Any],
) -> CompleteResult:
    """Validate IdP response, JIT-provision the user, return the persisted row."""
    pending = await _STATE_CACHE.pop(state)
    if pending is None:
        raise SsoError("unknown or expired SSO state")
    conn = db.get(IdpConnection, pending.connection_id)
    if conn is None or not conn.enabled:
        raise SsoError("idp connection no longer available")
    # Ensure redirect_uri is forwarded so the provider can re-derive it.
    callback_params = dict(params)
    callback_params.setdefault("redirect_uri", pending.redirect_uri)
    claims = await pending.provider.complete(params=callback_params, state=state)
    user = jit_provision_user(db, claims=claims, conn=conn)
    return CompleteResult(user=user, claims=claims, connection=conn)


# ── JIT provisioning ───────────────────────────────────────────────────────


def jit_provision_user(
    db: Session, *, claims: UserClaims, conn: IdpConnection
) -> User:
    """Find or create the local user that matches the IdP claims.

    Match by lowercased email. On first SSO login a new ``User`` row is
    created and bound to ``conn.org_id``. Returning users have their
    ``org_id`` left untouched (the IdP doesn't outrank existing memberships).
    """
    email = claims.email.strip().lower()
    if not email:
        raise SsoError("idp claims missing email")
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(
            email=email,
            uuid=_uuid.uuid4(),
            org_id=conn.org_id,
            role="member",
            is_active=True,
            is_verified=True,
            name=claims.name,
        )
        db.add(user)
        db.flush()
    else:
        # Returning user — make sure they're not locked out.
        if not user.is_active:
            raise SsoError("user account disabled")
        if user.org_id is None:
            user.org_id = conn.org_id
        if not user.is_verified:
            user.is_verified = True
        if claims.name and not user.name:
            user.name = claims.name
        db.flush()
    return user


# ── sso_required policy ────────────────────────────────────────────────────


ORG_SETTING_SSO_REQUIRED = "auth.sso_required"


def is_sso_required(db: Session, *, org_id: _uuid.UUID) -> bool:
    """Return True if the org's ``auth.sso_required`` policy is set.

    Checks the ``org_settings`` KV first, then falls back to any
    :class:`IdpConnection` row carrying ``sso_required=True``.
    """
    from ai_portal.settings.service import get_org_setting

    flag = get_org_setting(db, org_id=org_id, key=ORG_SETTING_SSO_REQUIRED)
    if flag is True or flag == "true":
        return True
    row = db.scalars(
        select(IdpConnection).where(
            IdpConnection.org_id == org_id,
            IdpConnection.sso_required.is_(True),
            IdpConnection.enabled.is_(True),
        )
    ).first()
    return row is not None
