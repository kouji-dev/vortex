import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

test.describe.configure({ mode: 'serial' })

/** Pre-built SSE that mimics a tool-using stream (thinking + 2 tool calls + reply). */
function buildToolStreamSse(messageId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { kind: 'thinking' } }) +
    e({ type: 'item_start', item: { kind: 'memory', count: 1 } }) +
    e({ type: 'item_done', item: { kind: 'memory', status: 'done' } }) +
    e({ type: 'item_start', item: { kind: 'tool_call', tool: 'web_search', params: { query: 'latest news' } } }) +
    e({ type: 'item_done', item: { kind: 'tool_call', tool: 'web_search', status: 'done' } }) +
    e({ type: 'item_start', item: { kind: 'tool_call', tool: 'search_knowledge_base', params: { query: 'news' } } }) +
    e({ type: 'item_done', item: { kind: 'tool_call', tool: 'search_knowledge_base', status: 'done' } }) +
    e({ type: 'item_done', item: { kind: 'thinking' } }) +
    e({ type: 'delta', text: 'Here is the latest news based on my web search.' }) +
    e({ type: 'done', message_id: messageId })
  )
}

async function setupSseReplay(
  page: import('@playwright/test').Page,
  convId: number,
  sseText: string,
) {
  await page.route(`**/api/chat/conversations/${convId}/messages`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
      },
      body: sseText,
    })
  })
}

test.describe('Thinking block UI', () => {
  test('thinking block collapses to pill after stream ends', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const sse = buildToolStreamSse(convId * 100)

    await setupSseReplay(page, convId, sse)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })
    const toolCards = page.getByTestId('chat-tool-card')
    await expect(toolCards.first()).toBeHidden()
  })

  test('user can expand thinking block by clicking the pill', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const sse = buildToolStreamSse(convId * 100)

    await setupSseReplay(page, convId, sse)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })

    await pill.click()
    const block = page.getByTestId('chat-thinking-block')
    await expect(block).toBeVisible()
    await expect(block.getByTestId('chat-tool-card').first()).toBeVisible()
  })

  test('user can collapse thinking block by clicking pill again', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const sse = buildToolStreamSse(convId * 100)

    await setupSseReplay(page, convId, sse)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })
    await pill.click()

    const block = page.getByTestId('chat-thinking-block')
    await expect(block).toBeVisible()

    await pill.click()
    const toolCards = page.getByTestId('chat-tool-card')
    await expect(toolCards.first()).toBeHidden()
  })

  test('tool cards show correct tool names after expanding', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const sse = buildToolStreamSse(convId * 100)

    await setupSseReplay(page, convId, sse)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })
    await pill.click()

    const block = page.getByTestId('chat-thinking-block')
    const names = block.getByTestId('chat-tool-card-name')
    await expect(names.first()).toBeVisible()
    const allNames = await names.allTextContents()
    expect(allNames.some(n => n.includes('Web Search'))).toBe(true)
  })

  test('tool cards show "done" status after stream ends', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const sse = buildToolStreamSse(convId * 100)

    await setupSseReplay(page, convId, sse)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })
    await pill.click()

    const block = page.getByTestId('chat-thinking-block')
    const statuses = block.getByTestId('chat-tool-card-status')
    const allStatuses = await statuses.allTextContents()
    expect(allStatuses.every(s => s.includes('done'))).toBe(true)
  })

  test('no thinking block for plain text reply (no item_start events)', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)

    const plainSse =
      'data: {"type":"delta","text":"Hello!"}\n\n' +
      'data: {"type":"done","message_id":999}\n\n'

    await page.route(`**/api/chat/conversations/${convId}/messages`, async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: plainSse,
      })
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('Say hello')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByText('Hello!')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('chat-thinking-block')).toBeHidden()
    await expect(page.getByTestId('chat-thinking-pill')).toBeHidden()
  })
})
