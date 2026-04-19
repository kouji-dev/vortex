import { test, expect } from '@playwright/test'

import { gotoChatComposerIndex } from '../support/conversation-ui'
import { createOrFindKb } from '../support/ui-helpers'

const E2E_CHAT_KB_SHARED = 'E2E Chat KB Shared'

test.describe.configure({ mode: 'serial' })

test.describe('Chat knowledge bases', () => {
  test('ensure shared KB for chat tests', async ({ page }) => {
    await createOrFindKb(page, E2E_CHAT_KB_SHARED)
  })

  test('attach KB via anchored popover', async ({ page }) => {
    await gotoChatComposerIndex(page)

    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
    await expect(page.getByTestId('kb-picker-search')).toBeVisible()

    await page.getByRole('option', { name: new RegExp(E2E_CHAT_KB_SHARED) }).click()
    await expect(page.getByText('Saving…')).toBeHidden({ timeout: 30_000 })

    await expect(
      page.getByRole('button', { name: /1 knowledge base active/i }),
    ).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('kb-picker-popover')).toBeHidden()

    await page.reload({ waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    const opt = page.getByRole('option', { name: new RegExp(E2E_CHAT_KB_SHARED) })
    await expect(opt).toContainText('Active')
  })
})
