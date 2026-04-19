import { test, expect } from '@playwright/test'
import { createOrFindConversation } from '../support/ui-helpers'

test.describe.configure({ mode: 'serial' })

const CONV_NAME = 'E2E Web Search Tool'

function buildWebSearchSse(messageId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { uid: 'uid-ws-1', kind: 'web_search', query: 'current oil price' } }) +
    e({ type: 'item_done', item: { uid: 'uid-ws-1', kind: 'web_search', query: 'current oil price', result_snippet: 'Brent crude at $82.40/barrel', status: 'done' } }) +
    e({ type: 'delta', text: 'Based on web search, oil is $80/barrel.' }) +
    e({ type: 'done', message_id: messageId })
  )
}

test.describe('web_search tool', () => {
  test('Test A — tool card renders during stream', async ({ page }) => {
    const convId = await createOrFindConversation(page, CONV_NAME)
    const messageId = convId * 1000 + 1
    const sseBody = buildWebSearchSse(messageId)

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      })
    })

    // Mock messages refetch so PersistedStreamItems shows chips after stream ends
    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: messageId,
              conversation_id: convId,
              role: 'assistant',
              content: 'Based on web search, oil is $80/barrel.',
              created_at: new Date().toISOString(),
              extra: {
                stream_items: [
                  { uid: 'uid-ws-1', kind: 'web_search', query: 'current oil price', result_snippet: 'Brent crude at $82.40/barrel', status: 'done' },
                ],
              },
            },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const textarea = page.getByRole('textbox', { name: /message/i })
    await textarea.fill('What is the current oil price?')
    await page.getByRole('button', { name: /send message/i }).click()

    // Wait for stream to complete
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const wsChip = page.locator('[data-testid="thread-item-chip"][data-kind="web_search"]')
    await expect(wsChip).toBeVisible()
    await expect(wsChip).toHaveAttribute('data-status', 'done')

    // Click to expand and check query in details
    await wsChip.getByTestId('thread-item-chip-toggle').click()
    const details = wsChip.locator('[data-testid="thread-item-details"]')
    await expect(details).toBeVisible()
    await expect(details).toContainText('current oil price')
  })

  test('Test B — assistant message rendered after stream', async ({ page }) => {
    const convId = await createOrFindConversation(page, CONV_NAME)
    const messageId = convId * 1000 + 2
    const sseBody = buildWebSearchSse(messageId)
    let streamCompleted = false

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      })
      streamCompleted = true
    })

    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET' && streamCompleted) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: messageId,
              conversation_id: convId,
              role: 'assistant',
              content: 'Based on web search, oil is $80/barrel.',
              created_at: new Date().toISOString(),
              extra: null,
            },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('What is the current oil price?')
    await page.getByRole('button', { name: /send message/i }).click()

    // Wait for stream to finish
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    // Assistant message with the synthesised content is in the thread
    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg).toContainText('Based on web search, oil is $80/barrel.')
  })
})
