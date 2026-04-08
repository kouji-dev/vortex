import { test, expect } from '@playwright/test'
import { createOrFindConversation } from '../support/ui-helpers'

test.describe.configure({ mode: 'serial' })

const CONV_NAME = 'E2E Web Search Tool'

function buildWebSearchSse(messageId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { kind: 'thinking' } }) +
    e({ type: 'item_start', item: { kind: 'tool_call', tool: 'web_search', params: { query: 'current oil price' } } }) +
    e({ type: 'item_done', item: { kind: 'tool_call', tool: 'web_search', status: 'done' } }) +
    e({ type: 'item_done', item: { kind: 'thinking' } }) +
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

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const textarea = page.getByRole('textbox', { name: /message/i })
    await textarea.fill('What is the current oil price?')
    await page.getByRole('button', { name: /send message/i }).click()

    // Thinking pill becomes visible once stream ends
    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })

    // Expand the thinking block to see tool cards
    await pill.click()
    const block = page.getByTestId('chat-thinking-block')
    await expect(block).toBeVisible()

    // Tool card for web_search is present with correct label
    const toolCard = block.getByTestId('chat-tool-card').first()
    await expect(toolCard).toBeVisible()
    await expect(toolCard.getByTestId('chat-tool-card-name')).toHaveText('Web Search')

    // Param span shows the query
    await expect(toolCard.getByTestId('chat-tool-card-param')).toHaveText('current oil price')

    // Status is done (not running)
    await expect(toolCard.getByTestId('chat-tool-card-status')).toHaveText('done')

    // Textarea re-enables after stream completes
    await expect(textarea).toBeEnabled({ timeout: 15_000 })
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
