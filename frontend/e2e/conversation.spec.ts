import { test, expect } from '@playwright/test'

import { createEmptyConversation } from './helpers/create-conversation'

test.describe('Chat conversation', () => {
  test('composer index shows message input', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(
      page.getByPlaceholder('Message the assistant… (Shift+Enter for newline)'),
    ).toBeVisible()
  })

  test('thread page shows composer and KB popover', async ({ page, request }) => {
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000'
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await expect(
      page.getByPlaceholder('Message the assistant… (Shift+Enter for newline)'),
    ).toBeVisible()

    await expect(page.getByTestId('chat-kb-picker-trigger')).toBeVisible()
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
    await expect(page.getByTestId('kb-picker-search')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('kb-picker-popover')).toBeHidden()
  })

  test('conversation metadata is visible', async ({ page, request }) => {
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000'
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await expect(page.getByText(/Created/i).first()).toBeVisible({ timeout: 15_000 })
  })
})
