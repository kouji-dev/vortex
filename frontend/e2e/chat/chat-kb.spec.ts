import { test, expect } from '@playwright/test'

import { createEmptyConversation } from '../support/create-conversation'
import { createKbThroughUi } from '../kb/helpers'

let kbName = ''

test.describe.configure({ mode: 'serial' })

test.describe('Chat knowledge bases', () => {
  test('create KB for chat tests', async ({ page }) => {
    kbName = `E2E Chat KB ${Date.now()}`
    await createKbThroughUi(page, kbName)
  })

  test('attach KB via anchored popover', async ({ page, request }) => {
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
    await expect(page.getByTestId('kb-picker-search')).toBeVisible()

    await page.getByRole('option', { name: new RegExp(kbName) }).click()
    await expect(page.getByText('Saving…')).toBeHidden({ timeout: 30_000 })

    await expect(
      page.getByRole('button', { name: /1 knowledge base active/i }),
    ).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('kb-picker-popover')).toBeHidden()

    await page.reload({ waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    const opt = page.getByRole('option', { name: new RegExp(kbName) })
    await expect(opt).toContainText('Active')
  })
})
