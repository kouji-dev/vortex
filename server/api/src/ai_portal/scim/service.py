"""ScimService — endpoint admin + RFC 7644 SCIM operations.

Two facets:

1. **Admin** — :class:`ScimEndpointService` mints bearer tokens, lists / revokes
   endpoints, and maps SCIM groups to control-plane system roles.
2. **Provisioning** — :class:`ScimProvisioner` executes RFC 7644 operations
   against the underlying User / Group tables. Deactivation revokes all
   sessions for the user and scopes (revokes) every API key the user owns.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ai_portal.api_keys.model import ApiKey
from ai_portal.auth.model import User, UserSession
from ai_portal.scim.model import (
    ScimEndpoint,
    ScimGroup,
    ScimGroupMember,
)
from ai_portal.scim.presets import MappedGroup, get_preset

TOKEN_PREFIX = "scim_"
TOKEN_BYTES = 32


# ── errors ────────────────────────────────────────────────────────────────────


class ScimError(Exception):
    """Base SCIM error. ``status`` mirrors the RFC 7644 HTTP status."""

    status: int = 400


class ScimNotFound(ScimError):
    status = 404


class ScimConflict(ScimError):
    status = 409


class ScimUnauthorized(ScimError):
    status = 401


class ScimEndpointDisabled(ScimError):
    status = 403


# ── token helpers ─────────────────────────────────────────────────────────────


def mint_scim_token() -> str:
    """Mint a fresh bearer token: ``scim_<32 random bytes hex>``."""
    return TOKEN_PREFIX + secrets.token_hex(TOKEN_BYTES)


def hash_scim_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


# ── admin service ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CreatedScimEndpoint:
    endpoint: ScimEndpoint
    token: str


class ScimEndpointService:
    """Org admin: create / list / revoke endpoints + group-role mapping."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_endpoint(
        self,
        *,
        org_id: _uuid.UUID,
        name: str,
        preset: str = "generic",
    ) -> CreatedScimEndpoint:
        token = mint_scim_token()
        endpoint = ScimEndpoint(
            org_id=org_id,
            name=name,
            preset=preset,
            token_hash=hash_scim_token(token),
        )
        self.db.add(endpoint)
        self.db.commit()
        self.db.refresh(endpoint)
        return CreatedScimEndpoint(endpoint=endpoint, token=token)

    def list_endpoints(self, org_id: _uuid.UUID) -> Sequence[ScimEndpoint]:
        return list(
            self.db.scalars(
                select(ScimEndpoint)
                .where(ScimEndpoint.org_id == org_id)
                .order_by(ScimEndpoint.created_at.desc())
            )
        )

    def revoke_endpoint(
        self, *, org_id: _uuid.UUID, endpoint_id: _uuid.UUID
    ) -> ScimEndpoint:
        row = self.db.scalars(
            select(ScimEndpoint).where(
                ScimEndpoint.id == endpoint_id,
                ScimEndpoint.org_id == org_id,
            )
        ).first()
        if row is None:
            raise ScimNotFound(f"endpoint {endpoint_id} not found")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            row.enabled = False
            self.db.commit()
            self.db.refresh(row)
        return row

    def set_group_role(
        self,
        *,
        endpoint_id: _uuid.UUID,
        org_id: _uuid.UUID,
        display_name: str,
        role_name: str | None,
    ) -> ScimGroup:
        """Upsert role mapping for a SCIM group by display name."""
        row = self.db.scalars(
            select(ScimGroup).where(
                ScimGroup.endpoint_id == endpoint_id,
                ScimGroup.display_name == display_name,
            )
        ).first()
        if row is None:
            row = ScimGroup(
                endpoint_id=endpoint_id,
                org_id=org_id,
                display_name=display_name,
                role_name=role_name,
            )
            self.db.add(row)
        else:
            row.role_name = role_name
        self.db.commit()
        self.db.refresh(row)
        return row

    def resolve_token(self, token: str | None) -> ScimEndpoint:
        """Look up the endpoint for *token* or raise :class:`ScimUnauthorized`."""
        if not token or not token.startswith(TOKEN_PREFIX):
            raise ScimUnauthorized("invalid SCIM token")
        row = self.db.scalars(
            select(ScimEndpoint).where(
                ScimEndpoint.token_hash == hash_scim_token(token)
            )
        ).first()
        if row is None or row.revoked_at is not None:
            raise ScimUnauthorized("invalid SCIM token")
        if not row.enabled:
            raise ScimEndpointDisabled("SCIM endpoint disabled")
        return row


# ── provisioner ──────────────────────────────────────────────────────────────


@dataclass
class _UserOpResult:
    user: User
    created: bool


class ScimProvisioner:
    """Execute SCIM RFC 7644 operations against the control-plane tables.

    All operations are scoped to a single :class:`ScimEndpoint` — the
    ``endpoint.org_id`` provides tenancy. The preset is resolved from
    ``endpoint.preset`` and translates inbound dicts to the flat
    :class:`MappedUser` / :class:`MappedGroup` shape.
    """

    def __init__(self, db: Session, endpoint: ScimEndpoint) -> None:
        self.db = db
        self.endpoint = endpoint
        self.preset = get_preset(endpoint.preset)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _touch_sync(self) -> None:
        self.endpoint.last_sync_at = datetime.now(UTC)

    def _find_user_by_external_id(self, external_id: str) -> User | None:
        return self.db.scalars(
            select(User).where(User.scim_external_id == external_id)
        ).first()

    def _find_user_by_email(self, email: str) -> User | None:
        return self.db.scalars(
            select(User).where(User.email == email.lower())
        ).first()

    # ── users ───────────────────────────────────────────────────────────────

    def create_user(self, payload: dict) -> _UserOpResult:
        mapped = self.preset.map_user(payload)
        # Conflict if a user with the same email or external_id exists.
        if mapped.external_id:
            existing = self._find_user_by_external_id(mapped.external_id)
            if existing is not None:
                raise ScimConflict(f"user already exists: {mapped.external_id}")
        existing_email = self._find_user_by_email(mapped.email)
        if existing_email is not None:
            raise ScimConflict(f"email already exists: {mapped.email}")

        user = User(
            email=mapped.email.lower(),
            name=mapped.name,
            locale=mapped.locale,
            org_id=self.endpoint.org_id,
            is_active=mapped.active,
            scim_external_id=mapped.external_id,
            role="member",
        )
        self.db.add(user)
        self.db.flush()
        if not mapped.active:
            self._cascade_deactivation(user)
        self._touch_sync()
        self.db.commit()
        self.db.refresh(user)
        return _UserOpResult(user=user, created=True)

    def get_user_by_scim_id(self, scim_id: str) -> User:
        # The SCIM resource ``id`` we expose to clients is the user's
        # ``scim_external_id`` if present, otherwise the user uuid.
        user = self._resolve_user(scim_id)
        if user is None:
            raise ScimNotFound(f"user {scim_id} not found")
        return user

    def replace_user(self, scim_id: str, payload: dict) -> User:
        """SCIM PUT — full replace."""
        user = self.get_user_by_scim_id(scim_id)
        mapped = self.preset.map_user(payload)
        was_active = user.is_active
        user.email = mapped.email.lower()
        user.name = mapped.name
        if mapped.locale is not None:
            user.locale = mapped.locale
        if mapped.external_id:
            user.scim_external_id = mapped.external_id
        user.is_active = mapped.active
        if was_active and not mapped.active:
            self._cascade_deactivation(user)
        self._touch_sync()
        self.db.commit()
        self.db.refresh(user)
        return user

    def patch_user(self, scim_id: str, payload: dict) -> User:
        """SCIM PATCH — apply ops from ``payload['Operations']``.

        Supports the subset used by Okta + Entra: ``replace`` and ``add``
        of top-level scalar fields (``active``, ``name``, ``userName``,
        ``emails[*].value``).
        """
        user = self.get_user_by_scim_id(scim_id)
        ops = payload.get("Operations") or payload.get("operations") or []
        was_active = user.is_active
        for op_ in ops:
            op_name = (op_.get("op") or "").lower()
            path = op_.get("path")
            value = op_.get("value")
            if op_name not in ("replace", "add"):
                continue
            # Entra / Okta most commonly send active toggles either as
            # path="active" + value=True/False or as a body without path:
            # value={"active": False}.
            if isinstance(value, dict) and path is None:
                if "active" in value:
                    user.is_active = bool(value["active"])
                if "displayName" in value:
                    user.name = value["displayName"]
                if "userName" in value:
                    user.email = str(value["userName"]).lower()
            else:
                if path == "active":
                    user.is_active = bool(value)
                elif path == "userName":
                    user.email = str(value).lower()
                elif path == "displayName" or path == "name.formatted":
                    user.name = str(value) if value else None
        if was_active and not user.is_active:
            self._cascade_deactivation(user)
        self._touch_sync()
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, scim_id: str) -> None:
        """SCIM DELETE — deactivate (per RFC convention, soft-delete)."""
        user = self.get_user_by_scim_id(scim_id)
        if user.is_active:
            user.is_active = False
            self._cascade_deactivation(user)
        self._touch_sync()
        self.db.commit()

    def list_users(self) -> list[User]:
        return list(
            self.db.scalars(
                select(User)
                .where(User.org_id == self.endpoint.org_id)
                .order_by(User.created_at.desc())
            )
        )

    def _resolve_user(self, scim_id: str) -> User | None:
        # Try by external id first, then by uuid.
        user = self._find_user_by_external_id(scim_id)
        if user is not None:
            return user
        try:
            uid = _uuid.UUID(scim_id)
        except ValueError:
            return None
        return self.db.scalars(select(User).where(User.uuid == uid)).first()

    def _cascade_deactivation(self, user: User) -> None:
        """Revoke sessions + scope API keys for a deactivated user.

        - Every active :class:`UserSession` gets ``revoked_at`` set.
        - Every active :class:`ApiKey` whose ``actor_user_id`` matches the
          deactivated user gets ``revoked_at`` set (the spec calls this
          "scope the keys" — we revoke them outright).
        """
        now = datetime.now(UTC)
        self.db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        self.db.execute(
            update(ApiKey)
            .where(
                ApiKey.actor_user_id == user.id,
                ApiKey.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    # ── groups ──────────────────────────────────────────────────────────────

    def create_group(self, payload: dict) -> ScimGroup:
        mapped = self.preset.map_group(payload)
        if not mapped.display_name:
            raise ScimError("displayName required")
        existing = self.db.scalars(
            select(ScimGroup).where(
                ScimGroup.endpoint_id == self.endpoint.id,
                ScimGroup.display_name == mapped.display_name,
            )
        ).first()
        if existing is not None:
            raise ScimConflict(f"group exists: {mapped.display_name}")

        group = ScimGroup(
            endpoint_id=self.endpoint.id,
            org_id=self.endpoint.org_id,
            external_id=mapped.external_id,
            display_name=mapped.display_name,
        )
        self.db.add(group)
        self.db.flush()
        self._sync_members(group, mapped)
        self._touch_sync()
        self.db.commit()
        self.db.refresh(group)
        return group

    def get_group(self, scim_id: str) -> ScimGroup:
        group = self._resolve_group(scim_id)
        if group is None:
            raise ScimNotFound(f"group {scim_id} not found")
        return group

    def replace_group(self, scim_id: str, payload: dict) -> ScimGroup:
        group = self.get_group(scim_id)
        mapped = self.preset.map_group(payload)
        if mapped.display_name:
            group.display_name = mapped.display_name
        if mapped.external_id is not None:
            group.external_id = mapped.external_id
        # Wipe + re-add members.
        self.db.execute(
            ScimGroupMember.__table__.delete().where(
                ScimGroupMember.group_id == group.id
            )
        )
        self._sync_members(group, mapped)
        self._touch_sync()
        self.db.commit()
        self.db.refresh(group)
        return group

    def patch_group(self, scim_id: str, payload: dict) -> ScimGroup:
        """SCIM PATCH for Group — supports the common Okta/Entra ops:

        - ``add`` / ``replace`` on ``members`` (full or single)
        - ``remove`` on ``members[value eq "..."]``
        - ``replace`` on ``displayName``
        """
        group = self.get_group(scim_id)
        ops = payload.get("Operations") or payload.get("operations") or []
        for op_ in ops:
            op_name = (op_.get("op") or "").lower()
            path = op_.get("path") or ""
            value = op_.get("value")
            if op_name == "replace" and path == "displayName":
                group.display_name = str(value)
            elif op_name in ("add", "replace") and path == "members":
                if op_name == "replace":
                    self.db.execute(
                        ScimGroupMember.__table__.delete().where(
                            ScimGroupMember.group_id == group.id
                        )
                    )
                mapped = self.preset.map_group({"members": value})
                self._sync_members(group, mapped)
            elif op_name == "remove" and path.startswith("members"):
                # path like: members[value eq "user-id"]
                external = _parse_members_filter(path)
                if external is not None:
                    self.db.execute(
                        ScimGroupMember.__table__.delete().where(
                            ScimGroupMember.group_id == group.id,
                            ScimGroupMember.external_user_id == external,
                        )
                    )
        self._touch_sync()
        self.db.commit()
        self.db.refresh(group)
        return group

    def delete_group(self, scim_id: str) -> None:
        group = self.get_group(scim_id)
        self.db.delete(group)
        self._touch_sync()
        self.db.commit()

    def list_groups(self) -> list[ScimGroup]:
        return list(
            self.db.scalars(
                select(ScimGroup)
                .where(ScimGroup.endpoint_id == self.endpoint.id)
                .order_by(ScimGroup.created_at.desc())
            )
        )

    def _resolve_group(self, scim_id: str) -> ScimGroup | None:
        try:
            gid = _uuid.UUID(scim_id)
        except ValueError:
            return self.db.scalars(
                select(ScimGroup).where(
                    ScimGroup.endpoint_id == self.endpoint.id,
                    ScimGroup.external_id == scim_id,
                )
            ).first()
        return self.db.scalars(
            select(ScimGroup).where(
                ScimGroup.endpoint_id == self.endpoint.id,
                ScimGroup.id == gid,
            )
        ).first()

    def _sync_members(self, group: ScimGroup, mapped: MappedGroup) -> None:
        """Persist members for a group. Resolves to users where possible."""
        seen: set[str] = set()
        for m in mapped.members:
            if m.external_user_id in seen:
                continue
            seen.add(m.external_user_id)
            user = self._find_user_by_external_id(m.external_user_id)
            if user is None and m.email:
                user = self._find_user_by_email(m.email)
            self.db.add(
                ScimGroupMember(
                    group_id=group.id,
                    org_id=self.endpoint.org_id,
                    user_id=(user.id if user else None),
                    external_user_id=m.external_user_id,
                )
            )


def _parse_members_filter(path: str) -> str | None:
    """Extract the ``value`` from ``members[value eq "..."]`` filters."""
    # Naive but sufficient for the Okta/Entra PATCH shape.
    import re

    match = re.search(r'value\s+eq\s+"([^"]+)"', path)
    if match:
        return match.group(1)
    match = re.search(r"value\s+eq\s+'([^']+)'", path)
    if match:
        return match.group(1)
    return None


# Public surface used by router type hints.
Op = Literal["create", "replace", "patch", "delete"]
