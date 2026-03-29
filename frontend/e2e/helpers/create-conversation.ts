import type { APIRequestContext } from '@playwright/test'

export async function createEmptyConversation(
  request: APIRequestContext,
  apiBase: string,
): Promise<number> {
  const base = apiBase.replace(/\/$/, '')
  const res = await request.post(`${base}/api/chat/conversations`, {
    headers: { Authorization: 'Bearer devtoken' },
    data: { title: 'E2E', model: null, assistant_id: null, settings: null },
  })
  if (!res.ok()) {
    throw new Error(`create conversation failed: ${res.status()} ${await res.text()}`)
  }
  const body = (await res.json()) as { id: number }
  return body.id
}
