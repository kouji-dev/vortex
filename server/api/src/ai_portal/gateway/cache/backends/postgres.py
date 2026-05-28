"""Postgres cache backend — ``prompt_cache_entries`` table.

No-Redis fallback. Rows are partitioned implicitly by ``org_id`` via RLS;
the backend pins ``app.current_org_id`` per session so isolation holds even
when the same factory is shared across orgs.

TTL is encoded as an absolute ``expires_at`` timestamp; reads filter on
``expires_at > now()`` and delete expired rows lazily.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class PostgresCache:
    """Cache backed by ``prompt_cache_entries``."""

    name = "postgres"

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        org_id: uuid.UUID | str,
    ) -> None:
        self._sf = session_factory
        self._org_id = uuid.UUID(str(org_id))

    async def _begin(self, session: AsyncSession) -> None:
        # Inline the literal — Postgres SET LOCAL rejects bound params.
        await session.execute(text(f"SET LOCAL app.current_org_id = '{self._org_id}'"))

    async def get(self, key: str) -> dict[str, Any] | None:
        async with self._sf() as s:
            await self._begin(s)
            row = (
                await s.execute(
                    text(
                        "SELECT value, expires_at <= now() AS expired "
                        "FROM prompt_cache_entries "
                        "WHERE org_id = :o AND cache_key = :k"
                    ),
                    {"o": str(self._org_id), "k": key},
                )
            ).first()
            if row is None:
                return None
            value, expired = row
            if expired:
                await s.execute(
                    text(
                        "DELETE FROM prompt_cache_entries "
                        "WHERE org_id = :o AND cache_key = :k"
                    ),
                    {"o": str(self._org_id), "k": key},
                )
                await s.commit()
                return None
            if isinstance(value, str):
                value = json.loads(value)
            return dict(value)

    async def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        if ttl <= 0:
            msg = f"ttl must be positive, got {ttl}"
            raise ValueError(msg)
        async with self._sf() as s:
            await self._begin(s)
            await s.execute(
                text(
                    "INSERT INTO prompt_cache_entries "
                    "(org_id, cache_key, value, expires_at, created_at) "
                    "VALUES (:o, :k, CAST(:v AS jsonb), "
                    "        now() + make_interval(secs => :ttl), now()) "
                    "ON CONFLICT (org_id, cache_key) DO UPDATE "
                    "SET value = EXCLUDED.value, "
                    "    expires_at = EXCLUDED.expires_at, "
                    "    created_at = EXCLUDED.created_at"
                ),
                {
                    "o": str(self._org_id),
                    "k": key,
                    "v": json.dumps(value, separators=(",", ":")),
                    "ttl": ttl,
                },
            )
            await s.commit()

    async def delete(self, key: str) -> None:
        async with self._sf() as s:
            await self._begin(s)
            await s.execute(
                text(
                    "DELETE FROM prompt_cache_entries "
                    "WHERE org_id = :o AND cache_key = :k"
                ),
                {"o": str(self._org_id), "k": key},
            )
            await s.commit()
