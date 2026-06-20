import { test, expect } from '../support/fixtures'
import { createEmptyConversation } from '../support/create-conversation'
import { installChatStreamMock, makeItem } from '../support/chat-mock'

test.describe.configure({ mode: 'serial' })

const MOCK_TURN_ID = '00000000-0000-4000-8000-000000000003'

/** Shared script: one kb_search tool_call followed by an assistant reply. */
function kbSearchScript(threadId: number) {
  return {
    threadId,
    turnId: MOCK_TURN_ID,
    userText: 'Summarise the project',
    toolCalls: [
      {
        tool_name: 'kb_search',
        params: { query: 'project summary' },
        result_snippet: 'Project overview: ...',
        provider: 'kb_search',
      },
    ],
    assistantText: 'Based on your documents, the project summary is...',
    turnItems: [
      makeItem(
        'tool_call',
        { tool_name: 'kb_search', params: { query: 'project summary' }, result_snippet: 'Project overview: ...' },
        { id: 1, threadId, turnId: MOCK_TURN_ID, provider: 'kb_search', latencyMs: 100 },
      ),
      makeItem(
        'assistant_text',
        { text: 'Based on your documents, the project summary is...' },
        { id: 2, threadId, turnId: MOCK_TURN_ID },
      ),
    ],
  }
}

test.describe('kb_search tool', () => {
  test('Test A — KB tool call item renders with kb_search name', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await installChatStreamMock(page, { conversationId: convId, script: kbSearchScript(convId) })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('textbox', { name: /message/i }).fill('Summarise the project')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg.getByTestId('tool-call-item')).toBeVisible()
    await expect(assistantMsg.getByTestId('tool-call-item')).toContainText('kb_search')
  })

  test('Test B — assistant message text is present after stream', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await installChatStreamMock(page, { conversationId: convId, script: kbSearchScript(convId) })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('textbox', { name: /message/i }).fill('Summarise the project')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg).toContainText('Based on your documents')
  })
})
