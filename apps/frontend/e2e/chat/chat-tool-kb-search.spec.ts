import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

test.describe.configure({ mode: 'serial' })

const MOCK_TURN_ID = '00000000-0000-4000-8000-000000000003'

function buildKbSearchSse(threadId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  const ts = new Date().toISOString()
  return (
    e({
      event_type: 'item',
      item: {
        id: 1,
        thread_id: threadId,
        turn_id: MOCK_TURN_ID,
        kind: 'tool_call',
        role: 'assistant',
        status: 'done',
        provider: 'kb_search',
        model: null,
        cost_usd: null,
        cost_estimated: false,
        latency_ms: 100,
        data: { tool_name: 'kb_search', params: { query: 'project summary' }, result_snippet: 'Project overview: ...' },
        parent_item_id: null,
        started_at: null,
        finished_at: null,
        created_at: ts,
      },
    }) +
    e({
      event_type: 'item',
      item: {
        id: 2,
        thread_id: threadId,
        turn_id: MOCK_TURN_ID,
        kind: 'assistant_text',
        role: 'assistant',
        status: 'done',
        provider: null,
        model: null,
        cost_usd: null,
        cost_estimated: false,
        latency_ms: null,
        data: { text: 'Based on your documents, the project summary is...' },
        parent_item_id: null,
        started_at: null,
        finished_at: null,
        created_at: ts,
      },
    }) +
    e({ event_type: 'done' })
  )
}

function buildMessagesResponse(threadId: number): object[] {
  const ts = new Date().toISOString()
  return [
    {
      id: 1,
      thread_id: threadId,
      turn_id: MOCK_TURN_ID,
      kind: 'tool_call',
      role: 'assistant',
      status: 'done',
      provider: 'kb_search',
      model: null,
      cost_usd: null,
      cost_estimated: false,
      latency_ms: 100,
      data: { tool_name: 'kb_search', params: { query: 'project summary' }, result_snippet: 'Project overview: ...' },
      parent_item_id: null,
      started_at: null,
      finished_at: null,
      created_at: ts,
    },
    {
      id: 2,
      thread_id: threadId,
      turn_id: MOCK_TURN_ID,
      kind: 'assistant_text',
      role: 'assistant',
      status: 'done',
      provider: null,
      model: null,
      cost_usd: null,
      cost_estimated: false,
      latency_ms: null,
      data: { text: 'Based on your documents, the project summary is...' },
      parent_item_id: null,
      started_at: null,
      finished_at: null,
      created_at: ts,
    },
  ]
}

test.describe('kb_search tool', () => {
  test('Test A — KB tool call item renders with kb_search name', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: buildKbSearchSse(convId) })
    })
    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildMessagesResponse(convId)) })
      } else {
        await route.continue()
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
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

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: buildKbSearchSse(convId) })
    })
    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildMessagesResponse(convId)) })
      } else {
        await route.continue()
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('Summarise the project')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg).toContainText('Based on your documents')
  })
})
