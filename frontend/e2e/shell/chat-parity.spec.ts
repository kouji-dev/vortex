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
    const seed = await request.post(
      `${apiBase}/api/chat/conversations/${convId}/e2e/seed-messages?pairs=52`,
      { headers: { Authorization: 'Bearer devtoken' } },
    )
    expect(
      seed.status(),
      `${await seed.text()} — use ./scripts/e2e-up.sh (E2E_ENABLE_CHAT_MESSAGES_SEED=1).`,
    ).toBe(200)
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
    const seed = await request.post(
      `${apiBase}/api/chat/conversations/${convId}/e2e/seed-messages?pairs=1`,
      { headers: { Authorization: 'Bearer devtoken' } },
    )
    expect(
      seed.status(),
      `${await seed.text()} — use ./scripts/e2e-up.sh (E2E_ENABLE_CHAT_MESSAGES_SEED=1).`,
    ).toBe(200)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const details = page.getByTestId('chat-starters-collapsed')
    await expect(details).toBeVisible({ timeout: 15_000 })
    await details.click()
    await expect(
      page.getByRole('button', { name: /summarize the key risks/i }),
    ).toBeVisible()
  })
})
