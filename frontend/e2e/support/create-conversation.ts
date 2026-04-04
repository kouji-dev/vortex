import type { APIRequestContext } from '@playwright/test'

/** Catalog slug seeded by `seed-catalog-models` — Claude Haiku 4.5 (fast / low cost for E2E). */
export const E2E_DEFAULT_CHAT_MODEL_SLUG = 'anthropic-claude-haiku-4-5' as const

export async function createEmptyConversation(
  request: APIRequestContext,
  apiBase: string,
  opts?: { model?: string | null },
): Promise<number> {
  const base = apiBase.replace(/\/$/, '')
  const model =
    opts === undefined || opts.model === undefined ? E2E_DEFAULT_CHAT_MODEL_SLUG : opts.model
  const res = await request.post(`${base}/api/chat/conversations`, {
    headers: { Authorization: 'Bearer devtoken' },
    data: {
      title: 'E2E',
      model,
      assistant_id: null,
      settings: null,
    },
  })
  if (!res.ok()) {
    throw new Error(`create conversation failed: ${res.status()} ${await res.text()}`)
  }
  const body = (await res.json()) as { id: number }
  return body.id
}
