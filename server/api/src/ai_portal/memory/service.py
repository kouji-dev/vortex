"""MemoryService — orchestrates extract / recall / CRUD / pause / export.

Service is the only place that talks to extractors, recallers, policies,
stores, audit, webhooks. Public surface is async.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.extractors import get as get_extractor
from ai_portal.memory.extractors.protocol import (
    Candidate,
    ExtractOpts,
    ExtractScope,
    Turn,
)
from ai_portal.memory.model import (
    ConflictStrategy,
    Memory,
    MemoryExtractionPolicy,
    MemoryPause,
    MemoryRecallPolicy,
    MemoryType,
    MemoryUse,
    ScopeKind,
)
from ai_portal.memory.policies import get as get_policy
from ai_portal.memory.recallers.protocol import (
    RecallFilters,
    RecallOpts,
    RecallScope,
    Recalled,
)
from ai_portal.memory.repository import MemoryRepo

logger = logging.getLogger(__name__)


# ── result types ────────────────────────────────────────────────────────


@dataclass
class ExtractResult:
    created: list[Memory] = field(default_factory=list)
    updated: list[Memory] = field(default_factory=list)
    skipped_sensitive: list[Candidate] = field(default_factory=list)
    skipped_dedup: list[Candidate] = field(default_factory=list)
    skipped_paused: bool = False
    skipped_module_disabled: bool = False


# ── helpers ─────────────────────────────────────────────────────────────


def _hash_query(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _coerce_org_uuid(v: Any) -> _uuid.UUID:
    return v if isinstance(v, _uuid.UUID) else _uuid.UUID(str(v))


async def _emit_audit_safe(**kw: Any) -> None:
    """Best-effort audit emit. Wraps the control-plane facade so service
    code stays sync-callable even when audit infra isn't wired."""
    try:
        from ai_portal.control_plane import emit_audit

        emit_audit(**kw)
    except Exception:
        logger.debug("memory.audit_emit_failed", extra=kw)


async def _emit_webhook_safe(event_type: str, payload: dict, org_id: _uuid.UUID) -> None:
    try:
        from ai_portal.control_plane import emit_webhook

        emit_webhook(event_type, payload, org_id)
    except Exception:
        logger.debug("memory.webhook_emit_failed", extra={"event": event_type})


async def _is_module_enabled(org_id: _uuid.UUID) -> bool:
    try:
        from ai_portal.control_plane import is_module_enabled

        return bool(is_module_enabled(org_id, "memory"))
    except Exception:
        # default-on when settings not wired
        return True


def _embedding_provider():
    """Returns an async function ``embed(text) -> list[float]`` or None."""
    try:
        from ai_portal.gateway import Actor, embed as gw_embed

        async def _embed(text: str, org_id: _uuid.UUID) -> list[float]:
            actor = Actor(org_id=org_id, user_id=None, kind="service")
            res = await gw_embed([text], model="text-embedding-3-small", actor=actor)
            data = getattr(res, "data", None) or []
            return list(data[0]) if data else []

        return _embed
    except Exception:
        return None


# ── service ─────────────────────────────────────────────────────────────


class MemoryService:
    """Orchestrate memory extract / recall / CRUD / pause / export."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        extractor_name: str | None = None,
        policy_name: str | None = None,
        embedder=None,
    ) -> None:
        from ai_portal.memory.deploy_config import default_for

        self.s = session
        self.repo = MemoryRepo(session)
        # Deploy-vs-runtime: unspecified provider falls back to the operator
        # default (which is the first declared / hard fallback when env unset).
        self.extractor_name = extractor_name or default_for("extractor")
        self.policy_name = policy_name or default_for("policy")
        self._embedder = embedder or _embedding_provider()

    # ── policy loaders ────────────────────────────────────────────────

    async def _load_extraction_policy(
        self, org_id: _uuid.UUID, scope_kind: ScopeKind
    ) -> MemoryExtractionPolicy | None:
        res = await self.s.execute(
            select(MemoryExtractionPolicy).where(
                MemoryExtractionPolicy.org_id == org_id,
                MemoryExtractionPolicy.scope_kind == scope_kind,
            )
        )
        return res.scalar_one_or_none()

    async def _load_recall_policy(
        self, org_id: _uuid.UUID, scope_kind: ScopeKind
    ) -> MemoryRecallPolicy | None:
        res = await self.s.execute(
            select(MemoryRecallPolicy).where(
                MemoryRecallPolicy.org_id == org_id,
                MemoryRecallPolicy.scope_kind == scope_kind,
            )
        )
        return res.scalar_one_or_none()

    async def _is_paused(
        self,
        org_id: _uuid.UUID,
        actor_user_id: int,
        scope_kind: ScopeKind | None,
        scope_id: str | None,
    ) -> bool:
        clauses: list[Any] = [
            MemoryPause.org_id == org_id,
            MemoryPause.actor_user_id == actor_user_id,
            MemoryPause.resumed_at.is_(None),
        ]
        res = await self.s.execute(select(MemoryPause).where(and_(*clauses)))
        rows = res.scalars().all()
        for r in rows:
            if r.scope_kind is None:  # global pause
                return True
            if r.scope_kind == scope_kind and (
                r.scope_id is None or r.scope_id == scope_id
            ):
                return True
        return False

    # ── extract path ─────────────────────────────────────────────────

    async def extract(
        self,
        turns: list[Turn],
        scope: ExtractScope,
        opts: ExtractOpts | None = None,
    ) -> ExtractResult:
        opts = opts or ExtractOpts()
        result = ExtractResult()
        org_uuid = _coerce_org_uuid(scope.org_id)

        # module flag
        if not await _is_module_enabled(org_uuid):
            result.skipped_module_disabled = True
            return result

        scope_kind_enum = ScopeKind(scope.scope_kind)
        try:
            actor_user_id = int(scope.actor_user_id)
        except (TypeError, ValueError):
            actor_user_id = 0

        if await self._is_paused(org_uuid, actor_user_id, scope_kind_enum, scope.scope_id):
            result.skipped_paused = True
            return result

        # apply policy overrides
        policy_row = await self._load_extraction_policy(org_uuid, scope_kind_enum)
        if policy_row:
            if policy_row.sensitive_block_json:
                opts.block_sensitive_categories = list(policy_row.sensitive_block_json)
            if policy_row.model_allow_json and opts.model not in policy_row.model_allow_json:
                await _emit_audit_safe(
                    org_id=org_uuid,
                    event_type="memory.extract.refused",
                    resource={"reason": "model_not_allowed", "model": opts.model},
                )
                return result
            conflict_strategy = policy_row.conflict_strategy
        else:
            conflict_strategy = ConflictStrategy.newer_wins

        policy = get_policy(self.policy_name)

        # pre-filter turns via policy
        filtered = []
        for t in turns:
            if not await policy.should_extract(t, scope):
                continue
            filtered.append(t)
        if not filtered:
            return result

        # extract candidates
        try:
            extractor = get_extractor(self.extractor_name)
            candidates = await extractor.extract(filtered, scope, opts)
        except Exception:
            logger.exception("memory.extract.failed")
            return result

        for cand in candidates:
            # sensitive gate
            hits = await policy.sensitive_category_match(cand.text)
            if hits:
                result.skipped_sensitive.append(cand)
                await _emit_audit_safe(
                    org_id=org_uuid,
                    event_type="memory.extract.refused",
                    resource={"reason": "sensitive", "categories": hits},
                )
                continue

            # dedupe / conflict resolution
            duplicate_of = await self._find_duplicate(
                org_uuid, cand, scope, scope_kind_enum
            )
            if duplicate_of is not None and opts.dedupe:
                merged = await self._apply_conflict(duplicate_of, cand, conflict_strategy)
                if merged is None:
                    result.skipped_dedup.append(cand)
                else:
                    result.updated.append(merged)
                continue

            persisted = await self._persist(cand, scope, scope_kind_enum, opts, org_uuid)
            if persisted is not None:
                result.created.append(persisted)
                await _emit_webhook_safe(
                    "memory.created",
                    {"memory_id": str(persisted.id), "type": cand.type},
                    org_uuid,
                )

        await _emit_audit_safe(
            org_id=org_uuid,
            event_type="memory.extract",
            resource={
                "created": len(result.created),
                "updated": len(result.updated),
                "skipped_sensitive": len(result.skipped_sensitive),
                "skipped_dedup": len(result.skipped_dedup),
            },
        )
        return result

    async def _find_duplicate(
        self,
        org_uuid: _uuid.UUID,
        cand: Candidate,
        scope: ExtractScope,
        scope_kind: ScopeKind,
    ) -> Memory | None:
        """Returns an existing Memory if cosine > 0.92 within same scope+type."""
        if self._embedder is None:
            return None
        try:
            emb = await self._embedder(cand.text, org_uuid)
        except Exception:
            return None
        if not emb:
            return None
        candidates = await self.repo.vector_search(
            org_id=org_uuid,
            embedding=emb,
            limit=3,
            type=MemoryType(cand.type),
        )
        for m, dist in candidates:
            if m.scope_kind != scope_kind:
                continue
            if str(scope.scope_id) not in [str(x) for x in (m.scope_ids_json or [])]:
                continue
            similarity = 1.0 - dist
            if similarity > 0.92:
                return m
        return None

    async def _apply_conflict(
        self, existing: Memory, cand: Candidate, strategy: ConflictStrategy
    ) -> Memory | None:
        if strategy == ConflictStrategy.keep_both:
            return None  # signal: do NOT update, caller should insert new
        if strategy == ConflictStrategy.prompt_user:
            await self.repo.patch(
                existing.id,
                confidence=min(0.5, float(existing.confidence or 0.5)),
            )
            return await self.repo.get(existing.id)
        # newer_wins: overwrite text, bump importance
        new_importance = min(1.0, float(existing.importance or 0.0) + 0.05)
        await self.repo.patch(
            existing.id,
            text=cand.text[:240],
            importance=new_importance,
            confidence=max(float(existing.confidence or 0.5), float(cand.confidence)),
        )
        return await self.repo.get(existing.id)

    async def _persist(
        self,
        cand: Candidate,
        scope: ExtractScope,
        scope_kind: ScopeKind,
        opts: ExtractOpts,
        org_uuid: _uuid.UUID,
    ) -> Memory | None:
        embedding = None
        if self._embedder is not None:
            try:
                embedding = await self._embedder(cand.text, org_uuid)
            except Exception:
                embedding = None
        # compute TTL using decay defaults
        from ai_portal.memory.decay import compute_expires_at

        expires_at = compute_expires_at(cand.type, retention_days=None)
        m = Memory(
            org_id=org_uuid,
            actor_owner_json={"kind": "user", "id": str(scope.actor_user_id)},
            scope_kind=scope_kind,
            scope_ids_json=[str(scope.scope_id)],
            type=MemoryType(cand.type),
            text=cand.text[:240],
            embedding=embedding,
            importance=0.5,
            confidence=float(cand.confidence),
            source_conversation_id=(
                int(scope.conversation_id)
                if scope.conversation_id is not None
                and str(scope.conversation_id).isdigit()
                else None
            ),
            source_turn_ids_json=list(cand.source_turn_ids),
            extractor_model=opts.model,
            tags_json=list(cand.tags),
            expires_at=expires_at,
        )
        return await self.repo.add(m)

    # ── recall path ──────────────────────────────────────────────────

    async def recall(
        self,
        query: str,
        scope: RecallScope,
        opts: RecallOpts | None = None,
        *,
        recaller_name: str = "vector_pgvector",
    ) -> list[Recalled]:
        opts = opts or RecallOpts()
        org_uuid = _coerce_org_uuid(scope.org_id)
        if not await _is_module_enabled(org_uuid):
            return []

        try:
            actor_user_id = int(scope.actor_user_id)
        except (TypeError, ValueError):
            actor_user_id = 0

        # gate via global pause
        if await self._is_paused(org_uuid, actor_user_id, None, None):
            return []

        # policy override of top_k / weights
        policy_row = await self._load_recall_policy(org_uuid, ScopeKind.user)
        if policy_row:
            opts.top_k = policy_row.top_k
            opts.recency_weight = float(policy_row.recency_weight)
            opts.importance_weight = float(policy_row.importance_weight)

        policy = get_policy(self.policy_name)
        if not await policy.should_recall(query, scope):
            return []

        # Deploy-vs-runtime: recaller must be in the operator-declared set.
        from ai_portal.memory.deploy_config import ProviderNotDeclared, validate_selection

        try:
            validate_selection("recaller", recaller_name)
        except ProviderNotDeclared:
            logger.warning("memory.recall.recaller_not_declared %s", recaller_name)
            return []

        # Use built-in vector_pgvector with this session by default
        if recaller_name == "vector_pgvector":
            from ai_portal.memory.recallers.vector_pgvector import (
                VectorPgvectorRecaller,
            )

            recaller = VectorPgvectorRecaller(self.s)
        else:
            from ai_portal.memory.recallers import get as get_recaller

            recaller = get_recaller(recaller_name)

        try:
            results = await recaller.recall(query, scope, opts)
        except Exception:
            logger.exception("memory.recall.failed")
            return []

        # filter by recall filters (types/scope_kinds/tags/time/source_assistant)
        if opts.filters:
            results = await self._apply_filters(results, opts.filters)
        return results[: opts.top_k]

    async def _apply_filters(
        self, results: list[Recalled], f: RecallFilters
    ) -> list[Recalled]:
        if not (f.types or f.scope_kinds or f.tags or f.time_from or f.time_to or f.source_assistant_id):
            return results
        # need to load Memory rows to filter
        ids = [_uuid.UUID(r.memory_id) for r in results]
        if not ids:
            return results
        rows = (
            await self.s.execute(select(Memory).where(Memory.id.in_(ids)))
        ).scalars().all()
        by_id = {str(m.id): m for m in rows}
        out: list[Recalled] = []
        for r in results:
            m = by_id.get(r.memory_id)
            if m is None:
                continue
            if f.types and m.type.value not in f.types:
                continue
            if f.scope_kinds and m.scope_kind.value not in f.scope_kinds:
                continue
            if f.tags and not any(t in (m.tags_json or []) for t in f.tags):
                continue
            if f.time_from and m.created_at.timestamp() < f.time_from:
                continue
            if f.time_to and m.created_at.timestamp() > f.time_to:
                continue
            out.append(r)
        return out

    async def attach_uses(
        self,
        results: list[Recalled],
        *,
        response_message_id: str,
        query: str = "",
    ) -> None:
        """Record provenance link between memory + response."""
        qhash = _hash_query(query)
        memory_ids: list[str] = []
        for r in results:
            await self.repo.record_use(
                memory_id=r.memory_id,
                query_text_hash=qhash,
                response_message_id=response_message_id,
                score=r.score,
            )
            memory_ids.append(r.memory_id)
        if memory_ids:
            # audit "memory.used"
            await _emit_audit_safe(
                event_type="memory.used",
                resource={
                    "response_message_id": response_message_id,
                    "memory_ids": memory_ids,
                },
            )

    # ── CRUD ─────────────────────────────────────────────────────────

    async def add_manual(
        self,
        *,
        org_id: _uuid.UUID,
        actor_user_id: int,
        type: str,
        text: str,
        scope_kind: str,
        scope_ids: list[str],
        importance: float = 0.5,
        confidence: float = 0.95,
        tags: list[str] | None = None,
        pinned: bool = False,
    ) -> Memory:
        from ai_portal.memory.decay import compute_expires_at

        # sensitive gate
        policy = get_policy(self.policy_name)
        hits = await policy.sensitive_category_match(text)
        if hits:
            await _emit_audit_safe(
                org_id=org_id,
                event_type="memory.extract.refused",
                resource={"reason": "sensitive_manual", "categories": hits},
            )
            raise ValueError(f"sensitive categories matched: {hits}")

        embedding = None
        if self._embedder is not None:
            try:
                embedding = await self._embedder(text, org_id)
            except Exception:
                embedding = None
        tags = list(tags or [])
        if "explicit_remember" not in tags:
            tags.append("explicit_remember")
        m = Memory(
            org_id=org_id,
            actor_owner_json={"kind": "user", "id": str(actor_user_id)},
            scope_kind=ScopeKind(scope_kind),
            scope_ids_json=[str(s) for s in scope_ids],
            type=MemoryType(type),
            text=text[:240],
            embedding=embedding,
            importance=importance,
            confidence=confidence,
            extractor_model="manual",
            tags_json=tags,
            pinned=pinned,
            expires_at=compute_expires_at(type, retention_days=None),
        )
        m = await self.repo.add(m)
        await _emit_audit_safe(
            org_id=org_id,
            event_type="memory.created",
            resource={
                "memory_id": str(m.id),
                "type": type,
                "source": "manual",
                "actor_user_id": actor_user_id,
                "scope_kind": scope_kind,
            },
        )
        await _emit_webhook_safe(
            "memory.created", {"memory_id": str(m.id), "type": type, "source": "manual"}, org_id
        )
        return m

    async def patch(
        self,
        memory_id: _uuid.UUID | str,
        *,
        text: str | None = None,
        importance: float | None = None,
        pinned: bool | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
    ) -> Memory | None:
        fields: dict[str, Any] = {}
        if text is not None:
            fields["text"] = text[:240]
        if importance is not None:
            fields["importance"] = max(0.0, min(1.0, importance))
        if pinned is not None:
            fields["pinned"] = pinned
        if tags is not None:
            fields["tags_json"] = list(tags)
        if confidence is not None:
            fields["confidence"] = max(0.0, min(1.0, confidence))
        if not fields:
            return await self.repo.get(memory_id)
        await self.repo.patch(memory_id, **fields)
        m = await self.repo.get(memory_id)
        if m is not None:
            await _emit_audit_safe(
                org_id=m.org_id,
                event_type="memory.updated",
                resource={
                    "memory_id": str(m.id),
                    "fields": sorted(fields.keys()),
                },
            )
            await _emit_webhook_safe(
                "memory.updated", {"memory_id": str(m.id)}, m.org_id
            )
        return m

    async def soft_delete(self, memory_id: _uuid.UUID | str) -> None:
        m = await self.repo.get(memory_id)
        if m is None:
            return
        await self.repo.soft_delete(memory_id)
        await _emit_audit_safe(
            org_id=m.org_id,
            event_type="memory.deleted",
            resource={"memory_id": str(m.id), "type": m.type.value},
        )
        await _emit_webhook_safe(
            "memory.deleted", {"memory_id": str(m.id)}, m.org_id
        )

    async def restore(self, memory_id: _uuid.UUID | str) -> Memory | None:
        m = await self.repo.get(memory_id)
        if m is None:
            return None
        if m.deleted_at and (datetime.utcnow() - m.deleted_at).days > 30:
            raise ValueError("memory hard-deletion window passed")
        await self.repo.restore(memory_id)
        restored = await self.repo.get(memory_id)
        await _emit_audit_safe(
            org_id=m.org_id,
            event_type="memory.restored",
            resource={"memory_id": str(m.id)},
        )
        await _emit_webhook_safe(
            "memory.restored", {"memory_id": str(m.id)}, m.org_id
        )
        return restored

    async def bulk_pin(
        self,
        *,
        org_id: _uuid.UUID,
        actor_user_id: int,
        ids: list[_uuid.UUID | str],
        pinned: bool,
    ) -> int:
        if not ids:
            return 0
        uuids = [_uuid.UUID(str(i)) for i in ids]
        res = await self.s.execute(
            update(Memory)
            .where(
                Memory.id.in_(uuids),
                Memory.org_id == org_id,
                Memory.deleted_at.is_(None),
            )
            .values(pinned=pinned)
        )
        await self.s.flush()
        count = int(res.rowcount or 0)
        await _emit_audit_safe(
            org_id=org_id,
            event_type="memory.bulk_pin",
            resource={"count": count, "pinned": pinned, "actor_user_id": actor_user_id},
        )
        return count

    async def bulk_tag(
        self,
        *,
        org_id: _uuid.UUID,
        actor_user_id: int,
        ids: list[_uuid.UUID | str],
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> int:
        """Add and/or remove tag values across multiple memories.

        Tags are stored in ``tags_json``. We load each row, dedupe the new
        list, and persist via ``patch``. Inefficient at scale but correct
        for any JSONB driver — bulk JSONB array mutation in pure SQL is
        error-prone with ON CONFLICT/DISTINCT semantics.
        """
        if not ids:
            return 0
        add_set = set(add or [])
        remove_set = set(remove or [])
        if not (add_set or remove_set):
            return 0
        uuids = [_uuid.UUID(str(i)) for i in ids]
        rows = (
            await self.s.execute(
                select(Memory).where(
                    Memory.id.in_(uuids),
                    Memory.org_id == org_id,
                    Memory.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        touched = 0
        for m in rows:
            existing = list(m.tags_json or [])
            new = [t for t in existing if t not in remove_set]
            for t in add_set:
                if t not in new:
                    new.append(t)
            if new != existing:
                await self.repo.patch(m.id, tags_json=new)
                touched += 1
        await _emit_audit_safe(
            org_id=org_id,
            event_type="memory.bulk_tag",
            resource={
                "count": touched,
                "add": list(add_set),
                "remove": list(remove_set),
                "actor_user_id": actor_user_id,
            },
        )
        return touched

    async def bulk_delete(
        self,
        *,
        org_id: _uuid.UUID,
        actor_user_id: int,
        ids: list[_uuid.UUID] | None = None,
        type: str | None = None,
        scope_kind: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> int:
        # If explicit ids provided
        if ids:
            count = await self.repo.bulk_soft_delete(
                [_uuid.UUID(str(i)) for i in ids]
            )
            await _emit_audit_safe(
                org_id=org_id,
                event_type="memory.bulk_deleted",
                resource={
                    "count": count,
                    "by_ids": True,
                    "actor_user_id": actor_user_id,
                },
            )
            return count
        clauses: list[Any] = [
            Memory.org_id == org_id,
            Memory.deleted_at.is_(None),
        ]
        actor_str = str(actor_user_id)
        clauses.append(
            or_(
                and_(
                    Memory.scope_kind == ScopeKind.user,
                    Memory.scope_ids_json.cast(JSONB).contains([actor_str]),
                ),
                and_(
                    Memory.scope_kind == ScopeKind.org,
                    Memory.scope_ids_json.cast(JSONB).contains([str(org_id)]),
                ),
            )
        )
        if type:
            clauses.append(Memory.type == MemoryType(type))
        if scope_kind:
            clauses.append(Memory.scope_kind == ScopeKind(scope_kind))
        if time_from:
            clauses.append(Memory.created_at >= time_from)
        if time_to:
            clauses.append(Memory.created_at <= time_to)
        res = await self.s.execute(
            update(Memory).where(and_(*clauses)).values(deleted_at=datetime.utcnow())
        )
        await self.s.flush()
        count = int(res.rowcount or 0)
        await _emit_audit_safe(
            org_id=org_id,
            event_type="memory.bulk_deleted",
            resource={
                "count": count,
                "by_ids": False,
                "type": type,
                "scope_kind": scope_kind,
                "actor_user_id": actor_user_id,
            },
        )
        return count

    # ── pause / resume ───────────────────────────────────────────────

    async def pause(
        self,
        *,
        org_id: _uuid.UUID,
        actor_user_id: int,
        scope_kind: str | None = None,
        scope_id: str | None = None,
    ) -> MemoryPause:
        sk = ScopeKind(scope_kind) if scope_kind else None
        existing = (
            await self.s.execute(
                select(MemoryPause).where(
                    MemoryPause.org_id == org_id,
                    MemoryPause.actor_user_id == actor_user_id,
                    MemoryPause.scope_kind == sk,
                    MemoryPause.scope_id == scope_id,
                    MemoryPause.resumed_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        p = MemoryPause(
            org_id=org_id,
            actor_user_id=actor_user_id,
            scope_kind=sk,
            scope_id=scope_id,
        )
        self.s.add(p)
        await self.s.flush()
        await _emit_audit_safe(
            org_id=org_id,
            event_type="memory.paused",
            resource={
                "actor_user_id": actor_user_id,
                "scope_kind": scope_kind,
                "scope_id": scope_id,
            },
        )
        return p

    async def resume(
        self,
        *,
        org_id: _uuid.UUID,
        actor_user_id: int,
        scope_kind: str | None = None,
        scope_id: str | None = None,
    ) -> int:
        sk = ScopeKind(scope_kind) if scope_kind else None
        res = await self.s.execute(
            update(MemoryPause)
            .where(
                MemoryPause.org_id == org_id,
                MemoryPause.actor_user_id == actor_user_id,
                MemoryPause.scope_kind == sk,
                MemoryPause.scope_id == scope_id,
                MemoryPause.resumed_at.is_(None),
            )
            .values(resumed_at=datetime.utcnow())
        )
        await self.s.flush()
        cleared = int(res.rowcount or 0)
        await _emit_audit_safe(
            org_id=org_id,
            event_type="memory.resumed",
            resource={
                "actor_user_id": actor_user_id,
                "scope_kind": scope_kind,
                "scope_id": scope_id,
                "cleared": cleared,
            },
        )
        return cleared

    # ── export ───────────────────────────────────────────────────────

    async def export_for_user(
        self,
        *,
        org_id: _uuid.UUID,
        user_id: int,
    ) -> dict[str, Any]:
        """Return a JSON-dict of all memories owned by user_id.

        Caller writes to BlobStore + signs the URL if desired.
        """
        rows = (
            await self.s.execute(
                select(Memory).where(
                    Memory.org_id == org_id,
                    Memory.actor_owner_json["id"].astext == str(user_id),
                )
            )
        ).scalars().all()
        await _emit_audit_safe(
            org_id=org_id,
            event_type="memory.exported",
            resource={"user_id": user_id, "count": len(rows)},
        )
        return {
            "memories": [
                {
                    "id": str(m.id),
                    "type": m.type.value,
                    "text": m.text,
                    "scope_kind": m.scope_kind.value,
                    "scope_ids": m.scope_ids_json,
                    "importance": float(m.importance),
                    "confidence": float(m.confidence),
                    "tags": m.tags_json,
                    "pinned": m.pinned,
                    "source_conversation_id": m.source_conversation_id,
                    "source_turn_ids": m.source_turn_ids_json,
                    "extractor_model": m.extractor_model,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "last_used_at": m.last_used_at.isoformat() if m.last_used_at else None,
                    "expires_at": m.expires_at.isoformat() if m.expires_at else None,
                    "deleted_at": m.deleted_at.isoformat() if m.deleted_at else None,
                }
                for m in rows
            ]
        }

    async def export_to_blob(
        self,
        *,
        org_id: _uuid.UUID,
        user_id: int,
    ) -> str:
        """Write export to BlobStore + return key (or presigned URL when supported)."""
        from ai_portal.control_plane import BlobStore, build_blob_store

        data = await self.export_for_user(org_id=org_id, user_id=user_id)
        payload = json.dumps(data).encode("utf-8")
        key = f"memory/exports/{org_id}/{user_id}/{int(time.time())}.json"
        try:
            store: BlobStore = build_blob_store()
            store.put(key, payload, content_type="application/json")
            try:
                return store.presigned_url(key, expires_in=3600)
            except Exception:
                return key
        except Exception:
            logger.exception("memory.export_blob_failed")
            return key
