"""Store protocol — pluggable memory persistence layer."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryStore(Protocol):
    name: str

    async def upsert(self, memory: Any) -> Any: ...

    async def delete(self, memory_id: str) -> None: ...

    async def list_for_actor(
        self,
        *,
        org_id: str,
        actor_user_id: str,
        team_ids: list[str] | None = None,
        **kw: Any,
    ) -> list[Any]: ...

    async def search(
        self,
        *,
        org_id: str,
        embedding: list[float],
        limit: int = 20,
        **kw: Any,
    ) -> list[tuple[Any, float]]: ...
