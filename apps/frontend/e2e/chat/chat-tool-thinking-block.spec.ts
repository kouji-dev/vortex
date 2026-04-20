import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

test.describe.configure({ mode: 'serial' })

const MOCK_TURN_ID = '00000000-0000-4000-8000-000000000099'

function makeItem(
  id: number,
  threadId: number,
  kind: string,
  data: object,
  opts: Partial<{ role: string; status: string; provider: string; model: string }> = {},
) {
  return {
    id,
    thread_id: threadId,
    turn_id: MOCK_TURN_ID,
    kind,
    role: opts.role ?? 'assistant',
    status: opts.status ?? 'done',
    provider: opts.provider ?? null,
    model: opts.model ?? null,
    cost_usd: null,
    cost_estimated: false,
    latency_ms: null,
    data,
    parent_item_id: null,
    started_at: null,
    finished_at: null,
    created_at: new Date().toISOString(),
  }
}

function buildToolStreamSse(threadId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({
      event_type: 'item',
      item: makeItem(
        1,
        threadId,
        'tool_call',
        { tool_name: 'web_search', params: { query: 'latest news' }, result_snippet: 'Top news results...' },
        { provider: 'web_search' },
      ),
    }) +
    e({
      event_type: 'item',
      item: makeItem(2, threadId, 'assistant_text', { text: 'Here is the latest news based on my web search.' }),
    }) +
    e({ event_type: 'done' })
  )
}

function buildMessagesResponse(threadId: number): object[] {
  return [
    { ...makeItem(1, threadId, 'user_message', { text: 'What is the latest news?', attachments: [] }, { role: 'user' }) },
    { ...makeItem(2, threadId, 'tool_call', { tool_name: 'web_search', params: { query: 'latest news' }, result_snippet: 'Top news results...' }, { provider: 'web_search' }) },
    { ...makeItem(3, threadId, 'assistant_text', { text: 'Here is the latest news based on my web search.' }) },
  ]
}

test.describe('Thread item rendering', () => {
  test('tool call tool name is visible in assistant message', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: buildToolStreamSse(convId) })
    })
    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildMessagesResponse(convId)) })
      } else {
        await route.continue()
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
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

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: buildToolStreamSse(convId) })
    })
    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildMessagesResponse(convId)) })
      } else {
        await route.continue()
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    await expect(page.getByTestId('chat-message-assistant').last()).toContainText('latest news')
  })

  test('plain text reply has no tool items', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const turnId = '00000000-0000-4000-8000-000000000088'

    const plainSse =
      `data: ${JSON.stringify({ event_type: 'item', item: { id: 1, thread_id: convId, turn_id: turnId, kind: 'assistant_text', role: 'assistant', status: 'done', provider: null, model: null, cost_usd: null, cost_estimated: false, latency_ms: null, data: { text: 'Hello!' }, parent_item_id: null, started_at: null, finished_at: null, created_at: new Date().toISOString() } })}\n\n` +
      'data: {"event_type":"done"}\n\n'

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: plainSse,
      })
    })
    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 1,
              thread_id: convId,
              turn_id: turnId,
              kind: 'assistant_text',
              role: 'assistant',
              status: 'done',
              provider: null,
              model: null,
              cost_usd: null,
              cost_estimated: false,
              latency_ms: null,
              data: { text: 'Hello!' },
              parent_item_id: null,
              started_at: null,
              finished_at: null,
              created_at: new Date().toISOString(),
            },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('Say hello')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })
    await expect(page.getByTestId('tool-call-item')).toHaveCount(0)
  })
})
