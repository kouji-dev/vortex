import type { APIRequestContext } from '@playwright/test'

const authHeaders = () => ({
  Authorization: `Bearer ${process.env.E2E_BEARER_TOKEN ?? 'devtoken'}`,
})

/**
 * All paths are relative so requests use Playwright `baseURL` (Vite dev server proxy).
 * That keeps the browser and API helpers on the same backend as `VITE_DEV_API_PROXY_TARGET`.
 */

export async function createMemoryViaApi(
  request: APIRequestContext,
  content: string,
): Promise<number> {
  const res = await request.post('/api/users/me/memories', {
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    data: { content },
  })
  if (res.status() !== 201) {
    throw new Error(`create memory failed: ${res.status()} ${await res.text()}`)
  }
  const body = (await res.json()) as { id: number; is_system?: boolean }
  if (body.is_system === true) {
    throw new Error('expected manual memory (is_system must not be true)')
  }
  return body.id
}

export async function deleteMemoryViaApi(
  request: APIRequestContext,
  id: number,
): Promise<void> {
  await request.delete(`/api/users/me/memories/${id}`, {
    headers: authHeaders(),
  })
}
