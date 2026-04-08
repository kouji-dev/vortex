/**
 * Chat spec parity — tests that do not require a live LLM (Step 1 harness).
 *
 * Run against E2E stack: ./scripts/e2e-up.sh from repo root, then from frontend:
 *   pnpm test:e2e -- shell/chat-parity.spec.ts
 *
 * @see docs/superpowers/specs/2026-04-04-chat-remaining-features-delivery.md (Step 1)
 */
import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

test.describe('Chat — spec parity (no LLM)', () => {
  test('empty thread documents composer behavior in empty state', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: /start the conversation/i })).toBeVisible()
    await expect(
      page.getByText(/nothing is sent until you press send/i),
    ).toBeVisible()
  })

  test('when starters API returns sections, suggested prompts panel is visible', async ({
    page,
    request,
  }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const starters = page.getByTestId('chat-starters-suggested')
    await expect(starters).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/suggested prompts/i)).toBeVisible()
  })

  test('Add options opens capabilities menu with Reflection', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-add-options').click()
    await expect(page.getByRole('menuitem', { name: /reflection/i })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: /research/i })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: /web stance/i })).toBeVisible()
  })

  test('model selector is visible on thread page', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(page.getByTestId('chat-model-select')).toBeVisible()
  })

  test('short thread does not show load-older control', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(page.getByTestId('chat-load-older')).toHaveCount(0)
  })

  test('load older after bulk seed reveals earliest seeded user line', async ({
    page,
    request,
  }) => {
    const convId = await createEmptyConversation(request, apiBase)

    // Build 100 messages so canLoadOlder=true, plus an "older" batch with the earliest message
    const tailMessages = Array.from({ length: 100 }, (_, i) => ({
      id: i + 1,
      conversation_id: convId,
      role: i % 2 === 0 ? 'user' : 'assistant',
      content: `E2E seed ${i % 2 === 0 ? 'user' : 'assistant'} ${i + 1}`,
      created_at: new Date(Date.now() - (100 - i) * 60_000).toISOString(),
      extra: null,
    }))
    const olderBatch = [
      {
        id: 0,
        conversation_id: convId,
        role: 'user',
        content: 'E2E seed user 0',
        created_at: new Date(Date.now() - 200 * 60_000).toISOString(),
        extra: null,
      },
    ]

    await page.route(`**/api/chat/conversations/${convId}/messages**`, async (route) => {
      const url = new URL(route.request().url())
      if (url.searchParams.has('before_id')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(olderBatch) })
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(tailMessages) })
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(page.getByTestId('chat-load-older')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('chat-load-older').click()
    await expect(page.getByText('E2E seed user 0', { exact: true })).toBeVisible({
      timeout: 20_000,
    })
  })

  test('with messages, suggested prompts can be opened from collapsible section', async ({
    page,
    request,
  }) => {
    const convId = await createEmptyConversation(request, apiBase)

    const messages = [
      {
        id: 1,
        conversation_id: convId,
        role: 'user',
        content: 'Hello',
        created_at: new Date().toISOString(),
        extra: null,
      },
    ]

    await page.route(`**/api/chat/conversations/${convId}/messages**`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(messages) })
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const details = page.getByTestId('chat-starters-collapsed')
    await expect(details).toBeVisible({ timeout: 15_000 })
    await details.click()
    await expect(
      page.getByRole('button', { name: /summarize the key risks/i }),
    ).toBeVisible()
  })
})
