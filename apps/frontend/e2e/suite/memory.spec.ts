/**
 * Cross-module: memory recall.
 *
 * Covers:
 *  - Send a turn in conversation A.
 *  - Start a new conversation B.
 *  - Memory recall surfaces in the new turn's memory sidebar.
 *
 * Chat turns + memory write/recall are all browser-mocked via the shared
 * `installChatStreamMock` / `installMemoriesMock` helpers.
 */
import { test, expect } from '../support/fixtures'

import { createOrFindConversation } from '../support/ui-helpers'
import { installChatStreamMock } from '../support/chat-mock'
import { installMemoriesMock } from '../support/memories-mock'

test.describe('Suite — Memory', () => {
  test('memory recall surfaces in a new conversation sidebar', async ({ page }) => {
    test.setTimeout(120_000)

    const MEMORY_CONTENT = `User prefers concise answers ${Date.now()}`

    // Mock memories list + recall — the memory only surfaces after a POST writes it.
    await installMemoriesMock(page, { content: MEMORY_CONTENT })

    // 1. Conversation A — send a turn that should generate a memory.
    await createOrFindConversation(page, 'E2E Memory Source A')
    const cleanupA = await installChatStreamMock(page, {
      script: { userText: 'Please be concise from now on.', assistantText: 'Got it — I will be concise.' },
    })
    await page.getByRole('textbox', { name: /message/i }).fill('Please be concise from now on.')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
      timeout: 60_000,
    })

    // Simulate the memory extractor having written the memory.
    await page.evaluate(async (content) => {
      await fetch('/api/users/me/memories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer devtoken' },
        body: JSON.stringify({ content }),
      })
    }, MEMORY_CONTENT)

    // 2. Conversation B — start a new conversation.
    await cleanupA()
    await createOrFindConversation(page, `E2E Memory Target B ${Date.now()}`)
    const cleanupB = await installChatStreamMock(page, {
      script: { userText: 'Summarise our chat.', assistantText: 'Short summary.' },
    })
    await page.getByRole('textbox', { name: /message/i }).fill('Summarise our chat.')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
      timeout: 60_000,
    })

    // 3. Memory sidebar should surface the recalled memory.
    //    Surface uses one of: data-testid="memory-sidebar", "memory-recall-list", "memory-chip".
    const sidebar = page
      .getByTestId('memory-sidebar')
      .or(page.getByTestId('memory-recall-list'))
      .or(page.getByRole('region', { name: /memor/i }))
      .first()
    await expect(sidebar).toBeVisible({ timeout: 15_000 })
    await expect(sidebar.getByText(MEMORY_CONTENT)).toBeVisible({ timeout: 10_000 })

    await cleanupB()
  })
})
