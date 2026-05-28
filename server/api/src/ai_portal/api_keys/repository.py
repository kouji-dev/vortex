"""Repository — DB primitives for :class:`ApiKey`.

The service owns business rules (revoke / rotate / expiry). The repository is a
thin wrapper over SQLAlchemy queries keyed by org + id + hash.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api_keys.model import ApiKey


class ApiKeyRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def add(self, key: ApiKey) -> ApiKey:
        self.s.add(key)
        self.s.flush()
        return key

    def by_id(
        self, *, org_id: _uuid.UUID, key_id: _uuid.UUID
    ) -> ApiKey | None:
        return self.s.scalars(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.org_id == org_id)
        ).first()

    def by_hash(self, hash_hex: str) -> ApiKey | None:
        """Lookup a key by stored SHA-256 hash — used by the bearer strategy."""
        return self.s.scalars(
            select(ApiKey).where(ApiKey.hash == hash_hex)
        ).first()

    def list_for_org(self, org_id: _uuid.UUID) -> Sequence[ApiKey]:
        return list(
            self.s.scalars(
                select(ApiKey)
                .where(ApiKey.org_id == org_id)
                .order_by(ApiKey.created_at.desc())
            )
        )
