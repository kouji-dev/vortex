"""Internal KB search provider — wraps the federated hybrid search so the
same ``POST /v1/search`` UX works against owned knowledge bases.
"""
from __future__ import annotations

import logging
from typing import Any

from ai_portal.rag.search_providers.protocol import SearchProviderResult

log = logging.getLogger(__name__)


class InternalKbsProvider:
    """Search over a list of internal KBs via federated hybrid search."""

    name = "internal_kbs"

    def __init__(
        self,
        db_factory=None,
        kb_ids: list[int] | None = None,
    ):
        """`db_factory()` should return a SQLAlchemy `Session`.

        `kb_ids` is the federation scope; can be overridden per call via the
        kwarg ``kb_ids=``.
        """
        self._db_factory = db_factory
        self._kb_ids = list(kb_ids or [])

    def search(
        self,
        query: str,
        *,
        num_results: int = 5,
        kb_ids: list[int] | None = None,
        **_: Any,
    ) -> list[SearchProviderResult]:
        from ai_portal.rag.search.federated import (
            FederatedRequest,
            federated_search,
        )

        ids = kb_ids if kb_ids is not None else self._kb_ids
        if not ids or self._db_factory is None:
            return []
        db = self._db_factory()
        try:
            req = FederatedRequest(query=query, kb_ids=ids, top_k=num_results)
            hits = federated_search(db, req)
        except Exception:  # noqa: BLE001
            log.exception("internal_kbs search failed: %r", query)
            return []
        results: list[SearchProviderResult] = []
        for h in hits:
            results.append(
                SearchProviderResult(
                    title=str((h.meta or {}).get("title") or h.document_id),
                    url=str((h.meta or {}).get("source_uri") or ""),
                    snippet=h.text[:240],
                    score=h.score,
                    source=f"kb:{h.kb_id}",
                    meta={
                        "chunk_id": h.chunk_id,
                        "document_id": h.document_id,
                        "kb_id": h.kb_id,
                    },
                )
            )
        return results
