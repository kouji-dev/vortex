"""search_knowledge_base tool — active when KB IDs are present.

Owns its schema, execution, and system prompt instruction.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

SYSTEM_PROMPT = (
    "Use search_knowledge_base for questions the user's documents can answer. "
    "Cite as [Source: filename]."
)


def system_prompt() -> str:
    return SYSTEM_PROMPT


def schema(kb_ids: list[int]) -> dict:  # noqa: ARG001 — kb_ids reserved for future per-kb config
    return {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search attached knowledge bases for relevant context. "
                "Call when you need document information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "kb_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "KB IDs to search",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Optional: number of results",
                    },
                },
                "required": ["query", "kb_ids"],
            },
        },
    }


def execute(
    query: str,
    kb_ids: list[int],
    top_k: int | None,
    db: Session,
) -> dict:
    from ai_portal.rag.service import search_knowledge_base_tool  # local import avoids circular dep

    result = search_knowledge_base_tool(db, query=query, kb_ids=kb_ids, top_k=top_k)
    content = result.get("context") or "No relevant context found."
    snippet = content[:500]
    # Per-chunk refs sized to the KbChunkRef payload — the streaming loop
    # persists these inside the kb_search ThreadItem so the user can see
    # exactly which document fragments grounded the answer.
    chunks_meta: list[dict] = []
    for c in result.get("citations", []):
        chunks_meta.append({
            "document_id": int(c.get("document_id") or 0),
            "document_name": str(c.get("document_name") or c.get("filename") or "unknown"),
            "kb_id": int(c.get("kb_id") or 0),
            "kb_name": str(c.get("kb_name") or ""),
            "chunk_id": int(c["chunk_id"]) if c.get("chunk_id") is not None else None,
            "score": float(c.get("score") or 0.0),
            "snippet": str(c.get("snippet") or ""),
        })
    return {
        "name": "search_knowledge_base",
        "content": content,
        "result_snippet": snippet,
        "chunks_meta": chunks_meta,
        "_used_kbs": result.get("used_kbs", []),
        "provider": "kb_search",
        "cost_usd": Decimal("0"),
    }
