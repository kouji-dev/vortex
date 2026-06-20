import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

import { escapeRegExp } from '../kb/helpers'
import { e2eStableResourceName } from './resource-slug'

/**
 * Wait until the app has hydrated client-side. The root sets
 * `html[data-hydrated="true"]` from a useEffect, which commits only after
 * hydration — so clicks/toggles after this won't be dropped by the SSR race.
 */
export async function waitForHydrated(page: Page): Promise<void> {
  await page.waitForFunction(() => document.documentElement.dataset.hydrated === 'true', {
    timeout: 30_000,
  })
}

/** Open the chat composer on `/chat/conversations` (no persisted thread id yet). */
export async function gotoChatComposerIndex(page: Page): Promise<void> {
  await page.goto('/chat/conversations', { waitUntil: 'domcontentloaded' })
  await waitForHydrated(page)
}

/**
 * Parse `/chat/conversations/:id` from the current URL.
 * @throws if the URL does not contain a numeric conversation id
 */
export function parseConversationIdFromUrl(page: Page): number {
  const m = page.url().match(/\/chat\/conversations\/(\d+)/)
  if (!m) throw new Error(`expected /chat/conversations/:id in URL, got ${page.url()}`)
  return Number(m[1])
}

/**
 * Ensure a persisted conversation exists whose sidebar title matches `title` (seeded from the
 * first user message). Opens it and returns its id. Creates it via the UI if missing.
 */
/**
 * Opens or creates (via first send) a conversation keyed by the Playwright test title.
 * Reuses the same sidebar row across runs to limit DB growth.
 */
export async function ensureConversationForTest(page: Page, testTitle: string): Promise<number> {
  return ensureConversationByTitle(page, e2eStableResourceName('conv', testTitle))
}

export async function ensureConversationByTitle(page: Page, title: string): Promise<number> {
  await gotoChatComposerIndex(page)
  const link = page.getByRole('link', { name: title, exact: true })
  if (await link.first().isVisible().catch(() => false)) {
    await link.first().click()
    await page.waitForURL(/\/chat\/conversations\/\d+/, { timeout: 30_000 })
    await waitForHydrated(page)
    return parseConversationIdFromUrl(page)
  }

  await page.getByRole('textbox', { name: /message/i }).fill(title)
  await page.getByRole('button', { name: /send message/i }).click()
  await page.waitForURL(/\/chat\/conversations\/\d+/, { timeout: 120_000 })
  await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
    timeout: 120_000,
  })
  await waitForHydrated(page)
  return parseConversationIdFromUrl(page)
}

/**
 * Start a new thread from the composer: first send creates the conversation (real stream unless
 * the caller registers routes). Returns the new conversation id.
 */
export async function createConversationThroughUi(
  page: Page,
  firstUserMessage: string,
): Promise<number> {
  await gotoChatComposerIndex(page)
  await page.getByRole('textbox', { name: /message/i }).fill(firstUserMessage)
  await page.getByRole('button', { name: /send message/i }).click()
  await page.waitForURL(/\/chat\/conversations\/\d+/, { timeout: 120_000 })
  await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
    timeout: 120_000,
  })
  await waitForHydrated(page)
  return parseConversationIdFromUrl(page)
}

/** Toggle a KB on the current chat thread via the composer KB picker (popover must be closed first). */
export async function attachKnowledgeBaseViaChatPicker(page: Page, kbName: string): Promise<void> {
  await page.getByTestId('chat-kb-picker-trigger').click()
  await page
    .getByRole('option', { name: new RegExp(escapeRegExp(kbName)) })
    .click()
  await expect(page.getByText('Saving…')).toBeHidden({ timeout: 30_000 })
}
