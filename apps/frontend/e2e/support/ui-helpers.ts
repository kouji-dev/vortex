import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

import { createKbThroughUi, escapeRegExp } from '../kb/helpers'

import { parseConversationIdFromUrl } from './conversation-ui'

const STREAM_ROUTE = '**/api/chat/conversations/*/messages/stream'

/**
 * Open an existing conversation from the sidebar by title, or create one via the composer with a
 * mocked stream so no LLM is required.
 */
export async function createOrFindConversation(page: Page, name: string): Promise<number> {
  await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
  const asideLink = page.locator('aside').getByRole('link', { name, exact: true })
  if (await asideLink.first().isVisible().catch(() => false)) {
    await asideLink.first().click()
    await page.waitForURL(/\/chat\/conversations\/\d+/, { timeout: 30_000 })
    return parseConversationIdFromUrl(page)
  }

  await page.route(STREAM_ROUTE, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'data: {"type":"delta","text":"OK"}\n\ndata: {"type":"done","message_id":1}\n\n',
    })
  })
  try {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill(name)
    await page.getByRole('button', { name: /send message/i }).click()
    await page.waitForURL(/\/chat\/conversations\/\d+/, { timeout: 120_000 })
    await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
      timeout: 120_000,
    })
    return parseConversationIdFromUrl(page)
  } finally {
    await page.unroute(STREAM_ROUTE)
  }
}

/**
 * Find a KB on the list page by name or create it via the dialog. Ends on `/knowledge-bases/:id`.
 */
export async function createOrFindKb(page: Page, name: string): Promise<number> {
  await page.goto('/knowledge-bases', { waitUntil: 'networkidle' })
  await page.getByLabel('Search knowledge bases').fill(name)
  const row = page.getByRole('row', { name: new RegExp(escapeRegExp(name)) })
  if (await row.first().isVisible().catch(() => false)) {
    const view = row.first().getByTitle('View knowledge base')
    const href = await view.getAttribute('href')
    const m = href?.match(/\/knowledge-bases\/(\d+)/)
    if (!m) throw new Error(`expected /knowledge-bases/:id in View link href, got ${href ?? 'null'}`)
    const id = Number(m[1])
    await view.click()
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${id}`))
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible({ timeout: 15_000 })
    return id
  }
  return createKbThroughUi(page, name)
}

/** Attach a knowledge base to the current persisted thread via the composer KB picker. */
export async function attachKbToConversationViaUi(page: Page, kbName: string): Promise<void> {
  await page.getByTestId('chat-kb-picker-trigger').click()
  await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
  const opt = page.getByRole('option', { name: new RegExp(escapeRegExp(kbName)) })
  await expect(opt).toBeVisible({ timeout: 15_000 })
  const label = await opt.textContent()
  const alreadyActive = (label ?? '').includes('Active')
  if (!alreadyActive) {
    await opt.click()
    await expect(
      page.getByTestId('kb-picker-popover-inner').getByText(/saving/i),
    ).toBeHidden({ timeout: 30_000 })
  }
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('kb-picker-popover')).toBeHidden({ timeout: 5_000 })
}
