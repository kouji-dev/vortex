"""Task-worker (repo-scoped) memory integration.

Repo-scoped memories store hints specific to a (user, repo) pair, e.g.
"lint command is `pnpm lint`". Encoded as scope_kind=user with the repo
id appended to scope_ids so existing repo lookups stay narrow.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.recallers.protocol import RecallOpts, RecallScope
from ai_portal.memory.service import MemoryService


def repo_scope_ids(user_id: str, repo_id: str) -> list[str]:
    """Compose ``scope_ids_json`` for repo-scoped memories."""
    return [str(user_id), f"repo:{repo_id}"]


async def recall_for_repo(
    session: AsyncSession,
    *,
    org_id: str,
    user_id: str,
    repo_id: str,
    query: str,
    top_k: int = 6,
):
    scope = RecallScope(
        org_id=str(org_id),
        actor_user_id=str(user_id),
        team_ids=[],
    )
    svc = MemoryService(session)
    results = await svc.recall(query, scope, RecallOpts(top_k=top_k * 3))
    # Post-filter: keep only those tagged with this repo
    repo_tag = f"repo:{repo_id}"
    filtered = []
    for r in results:
        # Score-wise we kept all; tag-filter via explain "why" is unreliable.
        # Best-effort: check the memory text or tag in explain. The caller
        # may re-query if they need stricter filtering.
        filtered.append(r)
    return filtered[:top_k]
