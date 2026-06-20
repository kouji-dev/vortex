import { test, expect } from '../support/fixtures'
import { createEmptyConversation } from '../support/create-conversation'
import { installChatStreamMock, makeItem } from '../support/chat-mock'

test.describe.configure({ mode: 'serial' })

const MOCK_TURN_ID = '00000000-0000-4000-8000-000000000002'

/** Shared script: one web_search tool_call followed by an assistant reply. */
function webSearchScript(threadId: number) {
  return {
    threadId,
    turnId: MOCK_TURN_ID,
    userText: 'What is the current oil price?',
    toolCalls: [
      {
        tool_name: 'web_search',
        params: { query: 'current oil price' },
        result_snippet: 'Brent crude at $82.40/barrel',
        provider: 'web_search',
      },
    ],
    assistantText: 'Based on web search, oil is $80/barrel.',
    turnItems: [
      makeItem(
        'tool_call',
        { tool_name: 'web_search', params: { query: 'current oil price' }, result_snippet: 'Brent crude at $82.40/barrel' },
        { id: 1, threadId, turnId: MOCK_TURN_ID, provider: 'web_search', latencyMs: 200 },
      ),
      makeItem(
        'assistant_text',
        { text: 'Based on web search, oil is $80/barrel.' },
        { id: 2, threadId, turnId: MOCK_TURN_ID },
      ),
    ],
  }
}

test.describe('web_search tool', () => {
  test('Test A — tool call item renders with web_search name', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await installChatStreamMock(page, { conversationId: convId, script: webSearchScript(convId) })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('textbox', { name: /message/i }).fill('What is the current oil price?')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg.getByTestId('tool-call-item')).toBeVisible()
    await expect(assistantMsg.getByTestId('tool-call-item')).toContainText('web_search')
  })

  test('Test B — assistant message rendered after stream', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await installChatStreamMock(page, { conversationId: convId, script: webSearchScript(convId) })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('textbox', { name: /message/i }).fill('What is the current oil price?')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg).toContainText('Based on web search')
  })
})
