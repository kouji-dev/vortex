import type { APIRequestContext } from '@playwright/test'

export async function createKnowledgeBase(
  request: APIRequestContext,
  apiBase: string,
  name: string,
): Promise<number> {
  const base = apiBase.replace(/\/$/, '')
  const res = await request.post(`${base}/api/knowledge-bases`, {
    headers: { Authorization: 'Bearer devtoken' },
    data: { name, description: '' },
  })
  if (!res.ok()) {
    throw new Error(`create KB failed: ${res.status()} ${await res.text()}`)
  }
  const body = (await res.json()) as { id: number }
  return body.id
}

export async function attachKnowledgeBasesToConversation(
  request: APIRequestContext,
  apiBase: string,
  conversationId: number,
  knowledgeBaseIds: number[],
): Promise<void> {
  const base = apiBase.replace(/\/$/, '')
  const res = await request.put(
    `${base}/api/chat/conversations/${conversationId}/knowledge-bases`,
    {
      headers: { Authorization: 'Bearer devtoken' },
      data: { knowledge_base_ids: knowledgeBaseIds },
    },
  )
  if (!res.ok()) {
    throw new Error(`attach KBs failed: ${res.status()} ${await res.text()}`)
  }
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
          'Grounded answer from E2E seed — the 📚 control should appear for this message only.',
      },
    },
  )
  return res.status()
}
