"""ACL filter applied to retrieval results.

Two entry points:

- :func:`filter_hits` — given a list of :class:`SearchHit` and an actor,
  drops hits whose chunks are not in the actor's allow set. Used as the
  server-side guard so retrieval never returns chunks the actor can't see,
  regardless of which retriever produced them.
- :func:`build_allow_predicate` — returns a ``(chunk_id) -> bool``
  callable so callers can filter without materialising the full set.

Deny-by-default: hits whose chunk has no row in ``kb_acls`` are dropped.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Callable, Iterable

from sqlalchemy.orm import Session

from ai_portal.rag.acl.service import visible_chunk_ids
from ai_portal.rag.search.types import SearchHit


def build_allow_predicate(
    db: Session,
    *,
    kb_id: int,
    actor_user_id: str | None,
    actor_group_ids: Iterable[str] = (),
) -> Callable[[str], bool]:
    """Return a fast ``(chunk_id) -> bool`` predicate for the given actor.

    Loads the full allow set once and then answers via set membership.
    """

    allow = visible_chunk_ids(
        db, kb_id=kb_id,
        user_id=actor_user_id,
        group_ids=actor_group_ids,
    )
    allow_str = {str(c) for c in allow}

    def _allows(chunk_id: str) -> bool:
        return chunk_id in allow_str

    return _allows


def filter_hits(
    db: Session,
    *,
    hits: list[SearchHit],
    kb_id: int,
    actor_user_id: str | None,
    actor_group_ids: Iterable[str] = (),
) -> list[SearchHit]:
    """Drop hits the actor isn't allowed to see.

    Empty input returns empty list — never queries the DB in that case.
    """

    if not hits:
        return []
    allows = build_allow_predicate(
        db, kb_id=kb_id,
        actor_user_id=actor_user_id,
        actor_group_ids=actor_group_ids,
    )
    return [h for h in hits if allows(h.chunk_id)]


def filter_hits_multi_kb(
    db: Session,
    *,
    hits: list[SearchHit],
    actor_user_id: str | None,
    actor_group_ids: Iterable[str] = (),
) -> list[SearchHit]:
    """ACL filter when hits span multiple KBs (federated search).

    Loads one allow set per distinct ``kb_id`` referenced in ``hits``.
    """

    if not hits:
        return []
    kb_ids = {h.kb_id for h in hits}
    predicates: dict[int, Callable[[str], bool]] = {
        kb_id: build_allow_predicate(
            db, kb_id=kb_id,
            actor_user_id=actor_user_id,
            actor_group_ids=actor_group_ids,
        )
        for kb_id in kb_ids
    }
    return [h for h in hits if predicates[h.kb_id](h.chunk_id)]


__all__ = [
    "build_allow_predicate",
    "filter_hits",
    "filter_hits_multi_kb",
]
