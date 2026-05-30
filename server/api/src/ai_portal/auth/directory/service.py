"""DirectoryService — LDAP/AD connection CRUD + bind orchestration.

Thin orchestrator: persists ``ldap_connections`` (bind secret encrypted), and
turns a connection row into a live :class:`DirectoryProvider` to authenticate /
test. On a successful bind it JIT-provisions the user and maps directory groups
to RBAC roles.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.directory.model import LdapConnection
from ai_portal.auth.directory.protocol import DirectoryProvider
from ai_portal.auth.directory.providers.ldap import (
    DirectoryAuthError,
    DirectoryConnectionError,
)
from ai_portal.auth.directory.registry import get_directory_provider
from ai_portal.auth.directory.secret_box import decrypt_secret, encrypt_secret
from ai_portal.auth.idp.protocol import UserClaims


class LdapConnectionNotFound(Exception):
    """Raised when a connection id is absent / not visible to the caller."""


class DirectoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── CRUD ─────────────────────────────────────────────────────────────
    def create(
        self,
        *,
        org_id: _uuid.UUID | None,
        name: str,
        kind: str,
        host: str,
        port: int | None,
        bind_dn: str,
        bind_secret: str,
        base_dn: str,
        user_filter: str | None,
        group_filter: str | None,
        tls_mode: str,
        attr_map: dict | None,
        group_role_map: dict | None,
        enabled: bool = True,
    ) -> LdapConnection:
        default_port = 636 if tls_mode == "ldaps" else 389
        conn = LdapConnection(
            org_id=org_id,
            name=name,
            kind=kind,
            host=host,
            port=port or default_port,
            bind_dn=bind_dn,
            bind_secret_enc=encrypt_secret(bind_secret),
            base_dn=base_dn,
            user_filter=user_filter or "(uid={username})",
            group_filter=group_filter,
            tls_mode=tls_mode,
            attr_map_json=attr_map,
            group_role_map_json=group_role_map,
            enabled=enabled,
        )
        self.db.add(conn)
        self.db.commit()
        self.db.refresh(conn)
        return conn

    def get(self, *, org_id: _uuid.UUID, conn_id: _uuid.UUID) -> LdapConnection:
        row = self.db.scalars(
            select(LdapConnection).where(
                LdapConnection.id == conn_id,
                LdapConnection.org_id == org_id,
            )
        ).first()
        if row is None:
            raise LdapConnectionNotFound(str(conn_id))
        return row

    def list_for_org(self, org_id: _uuid.UUID) -> Sequence[LdapConnection]:
        return list(
            self.db.scalars(
                select(LdapConnection)
                .where(LdapConnection.org_id == org_id)
                .order_by(LdapConnection.created_at.asc())
            )
        )

    def update(
        self, *, org_id: _uuid.UUID, conn_id: _uuid.UUID, **fields
    ) -> LdapConnection:
        row = self.get(org_id=org_id, conn_id=conn_id)
        secret = fields.pop("bind_secret", None)
        if secret:
            row.bind_secret_enc = encrypt_secret(secret)
        column_map = {
            "name": "name",
            "host": "host",
            "port": "port",
            "bind_dn": "bind_dn",
            "base_dn": "base_dn",
            "user_filter": "user_filter",
            "group_filter": "group_filter",
            "tls_mode": "tls_mode",
            "enabled": "enabled",
            "attr_map": "attr_map_json",
            "group_role_map": "group_role_map_json",
        }
        for key, col in column_map.items():
            if key in fields and fields[key] is not None:
                setattr(row, col, fields[key])
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, *, org_id: _uuid.UUID, conn_id: _uuid.UUID) -> None:
        row = self.get(org_id=org_id, conn_id=conn_id)
        self.db.delete(row)
        self.db.commit()

    # ── provider build ───────────────────────────────────────────────────
    def build_provider(self, conn: LdapConnection) -> DirectoryProvider:
        config = {
            "host": conn.host,
            "port": conn.port,
            "bind_dn": conn.bind_dn,
            "bind_secret": decrypt_secret(conn.bind_secret_enc),
            "base_dn": conn.base_dn,
            "user_filter": conn.user_filter,
            "group_filter": conn.group_filter,
            "tls_mode": conn.tls_mode,
            "attr_map": conn.attr_map_json or None,
            "group_role_map": conn.group_role_map_json or None,
        }
        return get_directory_provider(conn.kind, config)

    # ── operations ───────────────────────────────────────────────────────
    def test(self, *, org_id: _uuid.UUID, conn_id: _uuid.UUID) -> tuple[bool, str | None]:
        conn = self.get(org_id=org_id, conn_id=conn_id)
        try:
            provider = self.build_provider(conn)
            ok = provider.test_connection()
            return ok, None if ok else "service bind failed"
        except (DirectoryConnectionError, DirectoryAuthError) as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def authenticate(
        self, conn: LdapConnection, *, username: str, password: str
    ) -> UserClaims:
        provider = self.build_provider(conn)
        return provider.authenticate(username=username, password=password)


def resolve_connection_for_login(
    db: Session,
    *,
    connection_id: _uuid.UUID | None = None,
    org_slug: str | None = None,
) -> LdapConnection | None:
    """Find an enabled LDAP connection for a login attempt.

    Lookup order: explicit ``connection_id`` → first enabled connection on the
    org named by ``org_slug`` → first enabled per-deployment (org_id NULL)
    connection.
    """
    if connection_id is not None:
        return db.scalars(
            select(LdapConnection).where(
                LdapConnection.id == connection_id,
                LdapConnection.enabled.is_(True),
            )
        ).first()
    if org_slug:
        from ai_portal.auth.model import Org

        org = db.scalars(select(Org).where(Org.slug == org_slug)).first()
        if org is not None:
            conn = db.scalars(
                select(LdapConnection)
                .where(
                    LdapConnection.org_id == org.id,
                    LdapConnection.enabled.is_(True),
                )
                .order_by(LdapConnection.created_at.asc())
            ).first()
            if conn is not None:
                return conn
    # Per-deployment (org_id NULL) fallback.
    return db.scalars(
        select(LdapConnection)
        .where(
            LdapConnection.org_id.is_(None),
            LdapConnection.enabled.is_(True),
        )
        .order_by(LdapConnection.created_at.asc())
    ).first()
