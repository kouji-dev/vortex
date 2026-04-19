import type { APIRequestContext } from '@playwright/test'

/**
 * Seeds a conversation with a tool-call RAG response (simulates search_knowledge_base tool use).
 * Requires E2E_ENABLE_RAG_SEED=1 on the backend. Returns HTTP status.
 */
export async function seedRagToolCallForE2e(
  request: APIRequestContext,
  apiBase: string,
  conversationId: number,
  kbId: number,
  kbName: string,
): Promise<number> {
  const base = apiBase.replace(/\/$/, '')
  const res = await request.post(
    `${base}/api/chat/conversations/${conversationId}/e2e/seed-rag-assistant`,
    {
      headers: {
        Authorization: `Bearer ${process.env.E2E_BEARER_TOKEN ?? 'devtoken'}`,
        'Content-Type': 'application/json',
      },
      data: {
        kb_id: kbId,
        kb_name: kbName,
        assistant_content: 'This reply used the search_knowledge_base tool to find context.',
      },
    },
  )
  return res.status()
}

/** Dev API only when process has ``E2E_ENABLE_RAG_SEED=1``. Returns HTTP status. */
export async function seedRagAssistantForE2e(
  request: APIRequestContext,
  apiBase: string,
  conversationId: number,
  kbId: number,
  kbName: string,
): Promise<number> {
  const base = apiBase.replace(/\/$/, '')
  const res = await request.post(
    `${base}/api/chat/conversations/${conversationId}/e2e/seed-rag-assistant`,
    {
      headers: { Authorization: 'Bearer devtoken' },
      data: {
        kb_id: kbId,
        kb_name: kbName,
        assistant_content:
          'Grounded answer from E2E seed — retrieval was used for this reply only.',
      },
    },
  )
  return res.status()
}
