/**
 * Chat spec parity — tests that do not require a live LLM (Step 1 harness).
 *
 * Run against E2E stack: ./scripts/e2e-up.sh from repo root, then from frontend:
 *   pnpm test:e2e -- chat-parity.spec.ts
 *
 * @see docs/superpowers/specs/2026-04-04-chat-remaining-features-delivery.md (Step 1)
 */
import { test, expect } from '@playwright/test'
import { createEmptyConversation } from './helpers/create-conversation'

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
})
