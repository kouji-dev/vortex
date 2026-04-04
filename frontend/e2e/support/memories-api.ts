import type { APIRequestContext } from '@playwright/test'

const apiBase = () => process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

export async function createMemoryViaApi(
  request: APIRequestContext,
  content: string,
): Promise<number> {
  const base = apiBase().replace(/\/$/, '')
  const res = await request.post(`${base}/api/users/me/memories`, {
    headers: {
      Authorization: `Bearer ${process.env.E2E_BEARER_TOKEN ?? 'devtoken'}`,
      'Content-Type': 'application/json',
    },
    data: { content },
  })
  if (res.status() !== 201) {
    throw new Error(`create memory failed: ${res.status()} ${await res.text()}`)
  }
  const body = (await res.json()) as { id: number }
  return body.id
}

export async function deleteMemoryViaApi(
  request: APIRequestContext,
  id: number,
): Promise<void> {
  const base = apiBase().replace(/\/$/, '')
  await request.delete(`${base}/api/users/me/memories/${id}`, {
    headers: { Authorization: `Bearer ${process.env.E2E_BEARER_TOKEN ?? 'devtoken'}` },
  })
}
