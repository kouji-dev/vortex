import { test, expect } from '@playwright/test'
import { createOrFindConversation } from '../support/ui-helpers'

test('chat shows 3-col with inspector toggle', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/chat')
  await createOrFindConversation(page, 'E2E Shared Conversation')

  await expect(page.getByTestId('chat-layout')).toBeVisible()
  await expect(page.locator('.conv-list')).toBeVisible()
  await expect(page.locator('.chat-main')).toBeVisible()

  // Inspector closed by default.
  await expect(page.getByTestId('conversation-inspector')).toBeHidden()

  await page.getByTestId('toggle-inspector').click()
  await expect(page.getByTestId('conversation-inspector')).toBeVisible()

  await page.getByTestId('toggle-inspector').click()
  await expect(page.getByTestId('conversation-inspector')).toBeHidden()
})

test('chat collapses to single column on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/chat')
  // Mobile shows the conversation list as a drawer; main thread visible by default.
  await expect(page.locator('.chat-main')).toBeVisible()
})
