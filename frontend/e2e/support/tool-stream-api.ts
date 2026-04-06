import type { APIRequestContext } from '@playwright/test'

export async function seedToolStream(
  request: APIRequestContext,
  apiBase: string,
  conversationId: number,
): Promise<{ sse: string; message_id: string; conversation_id: string }> {
  const base = apiBase.replace(/\/$/, '')
  const res = await request.post(`${base}/api/e2e/seed-tool-stream`, {
    data: { conversation_id: conversationId },
    headers: { Authorization: 'Bearer devtoken' },
  })
  if (res.status() !== 201) throw new Error(`seed-tool-stream returned ${res.status()}: ${await res.text()}`)
  return res.json()
}
