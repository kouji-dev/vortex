/**
 * Frontend E2E runs against an in-memory mock backend
 * (`e2e/support/mock-server.mjs`, started by playwright.config `webServer`) —
 * no real backend / DB / Docker. SSR works because the mock serves BOTH the
 * server render and the client, so hydration matches.
 *
 * The `page` fixture wraps `page.goto` to wait for client hydration after every
 * navigation. The root sets `html[data-hydrated="true"]` from a useEffect (which
 * commits only post-hydration), so interactions after a goto won't be dropped by
 * the SSR race (a pre-hydration click hits the DOM but no React handler is
 * attached yet). In-app navigations (waitForURL after a click) wait explicitly
 * via `waitForHydrated`.
 *
 * Per-test stream customisation is layered on at the browser via
 * `installChatStreamMock` (page.route), which wins over the mock server.
 */
import { test as base, expect } from '@playwright/test'

export const test = base.extend({
  page: async ({ page }, use) => {
    const origGoto = page.goto.bind(page)
    page.goto = (async (url: string, opts?: Parameters<typeof origGoto>[1]) => {
      const res = await origGoto(url, opts)
      await page
        .waitForFunction(() => document.documentElement.dataset.hydrated === 'true', {
          timeout: 30_000,
        })
        .catch(() => {})
      return res
    }) as typeof page.goto
    await use(page)
  },
})

export { expect }
