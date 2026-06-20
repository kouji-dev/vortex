import { test, expect } from '../support/fixtures'
import { createEmptyConversation } from '../support/create-conversation'
import { installChatStreamMock, makeItem } from '../support/chat-mock'

test.describe.configure({ mode: 'serial' })

const MOCK_TURN_ID = '00000000-0000-4000-8000-000000000099'

/** Shared script: one web_search tool_call followed by an assistant reply. */
function toolScript(threadId: number) {
  return {
    threadId,
    turnId: MOCK_TURN_ID,
    userText: 'What is the latest news?',
    toolCalls: [
      {
        tool_name: 'web_search',
        params: { query: 'latest news' },
        result_snippet: 'Top news results...',
        provider: 'web_search',
      },
    ],
    assistantText: 'Here is the latest news based on my web search.',
    turnItems: [
      makeItem(
        'user_message',
        { text: 'What is the latest news?', attachments: [] },
        { id: 1, threadId, turnId: MOCK_TURN_ID, role: 'user' },
      ),
      makeItem(
        'tool_call',
        { tool_name: 'web_search', params: { query: 'latest news' }, result_snippet: 'Top news results...' },
        { id: 2, threadId, turnId: MOCK_TURN_ID, provider: 'web_search' },
      ),
      makeItem(
        'assistant_text',
        { text: 'Here is the latest news based on my web search.' },
        { id: 3, threadId, turnId: MOCK_TURN_ID },
      ),
    ],
  }
}

test.describe('Thread item rendering', () => {
  test('tool call tool name is visible in assistant message', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await installChatStreamMock(page, { conversationId: convId, script: toolScript(convId) })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg.getByTestId('tool-call-item')).toBeVisible()
    await expect(assistantMsg.getByTestId('tool-call-item')).toContainText('web_search')
  })

  test('assistant text is rendered after stream ends', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await installChatStreamMock(page, { conversationId: convId, script: toolScript(convId) })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    await expect(page.getByTestId('chat-message-assistant').last()).toContainText('latest news')
  })

  test('plain text reply has no tool items', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const turnId = '00000000-0000-4000-8000-000000000088'
    await installChatStreamMock(page, {
      conversationId: convId,
      script: {
        threadId: convId,
        turnId,
        userText: 'Say hello',
        assistantText: 'Hello!',
        turnItems: [
          makeItem('assistant_text', { text: 'Hello!' }, { id: 1, threadId: convId, turnId }),
        ],
      },
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('textbox', { name: /message/i }).fill('Say hello')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })
    await expect(page.getByTestId('tool-call-item')).toHaveCount(0)
  })
})
