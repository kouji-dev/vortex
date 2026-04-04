import type { APIRequestContext } from '@playwright/test'

const authHeaders = () => ({
  Authorization: `Bearer ${process.env.E2E_BEARER_TOKEN ?? 'devtoken'}`,
})

/**
 * All paths are relative so requests use Playwright `baseURL` (Vite dev server proxy).
 * That keeps the browser and API helpers on the same backend as `VITE_DEV_API_PROXY_TARGET`.
 */

/** Truncates E2E app data. Returns HTTP status (200 = ok, 403 = wrong database). */
export async function purgeE2eDatabase(request: APIRequestContext): Promise<number> {
  const res = await request.post('/api/e2e/purge', {
    headers: authHeaders(),
  })
  return res.status()
}

/** Inserts or updates the single system profile row. Returns HTTP status (201 = ok, 403 = wrong DB, 404 = route missing). */
export async function seedSystemMemoryForE2e(
  request: APIRequestContext,
  content: string,
): Promise<number> {
  const res = await request.post('/api/e2e/seed-system-memory', {
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    data: { content },
  })
  return res.status()
}

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
