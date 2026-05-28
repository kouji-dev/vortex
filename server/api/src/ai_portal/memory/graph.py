"""Memory graph traversal.

Treats every ``memory`` row of ``type == relation`` as an edge between two
entity memories. The edge endpoints live in either:

- ``tags_json`` — supports ``rel:<memory_id>`` markers, OR
- ``source_turn_ids_json`` — falls back to entity ids stored as turn ids, OR
- ``actor_owner_json["entities"]`` — a structured list of memory_id strings.

Given a seed memory_id, BFS the relation graph up to ``depth`` hops and
return all connected entity memories (deduped) plus the relation rows that
connected them. Pure async + SQL — no in-memory caching across requests.
"""
from __future__ import annotations

import uuid as _uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import Memory, MemoryType


# ── edge extraction ─────────────────────────────────────────────────────────


def _endpoints_of(rel: Memory) -> list[str]:
    """Pull connected memory_ids out of a relation memory's payload.

    Supports three encodings (first non-empty wins):
        1) ``actor_owner_json["entities"]`` — explicit list.
        2) ``tags_json`` items prefixed with ``rel:``.
        3) ``source_turn_ids_json`` raw UUID-like strings.
    """
    owner = rel.actor_owner_json or {}
    explicit = owner.get("entities") if isinstance(owner, dict) else None
    if explicit:
        return [str(x) for x in explicit if x]
    tagged = [
        t[len("rel:") :] for t in (rel.tags_json or []) if isinstance(t, str) and t.startswith("rel:")
    ]
    if tagged:
        return tagged
    return [str(x) for x in (rel.source_turn_ids_json or []) if x]


# ── result types ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class GraphNode:
    memory_id: str
    text: str
    type: str
    depth: int


@dataclass(slots=True)
class GraphEdge:
    relation_id: str
    text: str
    src: str
    dst: str


@dataclass(slots=True)
class GraphResult:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


# ── traversal ───────────────────────────────────────────────────────────────


async def _load_relations_touching(
    session: AsyncSession, org_id: _uuid.UUID, ids: Iterable[str]
) -> list[Memory]:
    ids = [str(x) for x in ids]
    if not ids:
        return []
    # Match in actor_owner_json.entities, tags_json (rel:<id>), source_turn_ids_json.
    tags_clauses = [
        Memory.tags_json.cast(JSONB).contains([f"rel:{i}"]) for i in ids
    ]
    turn_clauses = [Memory.source_turn_ids_json.cast(JSONB).contains([i]) for i in ids]
    entity_clauses = [
        Memory.actor_owner_json["entities"].cast(JSONB).contains([i]) for i in ids
    ]
    stmt = select(Memory).where(
        and_(
            Memory.org_id == org_id,
            Memory.deleted_at.is_(None),
            Memory.type == MemoryType.relation,
            or_(*(tags_clauses + turn_clauses + entity_clauses)),
        )
    )
    res = await session.execute(stmt)
    return list(res.scalars())


async def _load_memories(
    session: AsyncSession, org_id: _uuid.UUID, ids: Iterable[str]
) -> dict[str, Memory]:
    ids = [str(x) for x in ids]
    if not ids:
        return {}
    try:
        uuids = [_uuid.UUID(i) for i in ids]
    except ValueError:
        return {}
    res = await session.execute(
        select(Memory).where(
            Memory.org_id == org_id,
            Memory.id.in_(uuids),
            Memory.deleted_at.is_(None),
        )
    )
    return {str(m.id): m for m in res.scalars()}


async def traverse(
    session: AsyncSession,
    *,
    org_id: _uuid.UUID,
    seed_id: _uuid.UUID | str,
    depth: int = 2,
) -> GraphResult:
    """BFS from seed up to ``depth`` hops over relation memories."""
    depth = max(0, min(depth, 5))
    seed_str = str(seed_id)
    result = GraphResult()

    seed_map = await _load_memories(session, org_id, [seed_str])
    seed = seed_map.get(seed_str)
    if seed is None:
        return result
    result.nodes.append(
        GraphNode(memory_id=seed_str, text=seed.text, type=seed.type.value, depth=0)
    )

    visited_nodes: set[str] = {seed_str}
    visited_edges: set[str] = set()
    frontier: deque[tuple[str, int]] = deque([(seed_str, 0)])

    while frontier:
        node_id, d = frontier.popleft()
        if d >= depth:
            continue
        relations = await _load_relations_touching(session, org_id, [node_id])
        new_endpoint_ids: set[str] = set()
        for rel in relations:
            rid = str(rel.id)
            if rid in visited_edges:
                continue
            visited_edges.add(rid)
            endpoints = [e for e in _endpoints_of(rel) if e != node_id]
            for e in endpoints:
                result.edges.append(
                    GraphEdge(relation_id=rid, text=rel.text, src=node_id, dst=e)
                )
                if e not in visited_nodes:
                    new_endpoint_ids.add(e)
        if not new_endpoint_ids:
            continue
        endpoint_map = await _load_memories(session, org_id, new_endpoint_ids)
        for eid, mem in endpoint_map.items():
            if eid in visited_nodes:
                continue
            visited_nodes.add(eid)
            result.nodes.append(
                GraphNode(memory_id=eid, text=mem.text, type=mem.type.value, depth=d + 1)
            )
            frontier.append((eid, d + 1))

    return result


__all__ = [
    "GraphEdge",
    "GraphNode",
    "GraphResult",
    "traverse",
]
