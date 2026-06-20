/**
 * Browser-level Memories mocks for E2E.
 *
 * Mocks the memories list/write endpoint and the recall endpoint at the browser
 * via `page.route()` — no real extraction, embedding, or recall.
 *
 * The mock is stateful: a memory only surfaces in the list + recall after a POST
 * "writes" it, mimicking the extractor.
 */
import type { Page, Route } from '@playwright/test'

export const MEMORIES_ROUTE = '**/api/users/me/memories**'
export const RECALL_ROUTE = '**/api/memories/recall**'

export interface InstallMemoriesMockOpts {
  /** Memory id surfaced in list + recall. Defaults to 7777. */
  memoryId?: number
  /** Memory content. */
  content: string
  /** Recall score. Defaults to 0.88. */
  score?: number
}

export interface MemoriesMockHandle {
  /** True once a memory POST has been observed. */
  written: () => boolean
  cleanup: () => Promise<void>
}

/**
 * Route the memories list/write + recall endpoints. The memory only surfaces
 * after a POST writes it. Returns a handle with `written()` + `cleanup()`.
 */
export async function installMemoriesMock(
  page: Page,
  opts: InstallMemoriesMockOpts,
): Promise<MemoriesMockHandle> {
  const memoryId = opts.memoryId ?? 7777
  const score = opts.score ?? 0.88
  const { content } = opts

  let memoryWritten = false

  await page.route(MEMORIES_ROUTE, async (route: Route) => {
    if (route.request().method() === 'POST') {
      memoryWritten = true
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ id: memoryId, content, created_at: new Date().toISOString() }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        memoryWritten ? [{ id: memoryId, content, created_at: new Date().toISOString() }] : [],
      ),
    })
  })

  await page.route(RECALL_ROUTE, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: memoryWritten ? [{ id: memoryId, content, score }] : [] }),
    })
  })

  return {
    written: () => memoryWritten,
    cleanup: async () => {
      await page.unroute(MEMORIES_ROUTE).catch(() => undefined)
      await page.unroute(RECALL_ROUTE).catch(() => undefined)
    },
  }
}
