"""search_knowledge_base tool — active when KB IDs are present.

Owns its schema, execution, and system prompt instruction.
"""

from __future__ import annotations

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
    return {
        "name": "search_knowledge_base",
        "content": content,
        "_used_kbs": result.get("used_kbs", []),
    }
