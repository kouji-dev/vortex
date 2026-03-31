# Chat + embeddings: LangChain providers (completed)

**Status:** implemented in-tree.

Chat uses `LangChainChatProvider` (`ChatAnthropic` / `ChatOpenAI`) in
`backend/src/ai_portal/services/llm_providers/langchain_chat.py`. Embeddings use
`OpenAIEmbeddings` in `backend/src/ai_portal/services/embedding.py`.

Catalog rows expose vendor model strings in `catalog_models.api_model_id`.
`resolve_stored_model_to_chat_model` maps stored conversation slugs or bare API
ids to the string passed to LangChain.

Verification: from `backend/`, run `python -m ruff check src tests` and `pytest`.
