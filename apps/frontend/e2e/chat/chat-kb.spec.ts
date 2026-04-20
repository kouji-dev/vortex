import { test, expect } from '@playwright/test'

import { createOrFindConversation } from '../support/ui-helpers'
import { createOrFindKb } from '../support/ui-helpers'

const E2E_CHAT_KB_SHARED = 'E2E Chat KB Shared'
const E2E_CHAT_KB_CONV = 'E2E Chat KB Conv'

test.describe.configure({ mode: 'serial' })

test.describe('Chat knowledge bases', () => {
  test('ensure shared KB for chat tests', async ({ page }) => {
    await createOrFindKb(page, E2E_CHAT_KB_SHARED)
  })

  test('attach KB via anchored popover', async ({ page }) => {
    test.setTimeout(120_000)
    // Use a persisted conversation so KB attachment survives page reload (PATCH persists to DB).
    const convId = await createOrFindConversation(page, E2E_CHAT_KB_CONV)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
    await expect(page.getByTestId('kb-picker-search')).toBeVisible()

    const opt = page.getByRole('option', { name: new RegExp(E2E_CHAT_KB_SHARED) }).first()
    await expect(opt).toBeVisible({ timeout: 15_000 })
    // Detach if already attached (from a previous run) to ensure a clean attach cycle
    const alreadyActive = await opt.evaluate((el) => el.getAttribute('aria-selected') === 'true')
    if (alreadyActive) {
      await opt.click()
      await expect(opt).not.toContainText('Active', { timeout: 10_000 })
    }
    await opt.click()
    await expect(page.getByTestId('kb-picker-popover-inner').getByText(/saving/i)).toBeHidden({ timeout: 30_000 })

    await expect(
      page.getByRole('button', { name: /1 knowledge base active/i }),
    ).toBeVisible({ timeout: 10_000 })

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('kb-picker-popover')).toBeHidden()

    await page.waitForLoadState('networkidle')
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(
      page.getByRole('option', { name: new RegExp(E2E_CHAT_KB_SHARED) }).first(),
    ).toContainText('Active', { timeout: 15_000 })
  })
})
