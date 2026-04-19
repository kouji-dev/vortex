import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

test.describe.configure({ mode: 'serial' })

function buildToolStreamSse(messageId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { uid: 'uid-mem-1', kind: 'memory', count: 1 } }) +
    e({ type: 'item_done', item: { uid: 'uid-mem-1', kind: 'memory', count: 1, status: 'done' } }) +
    e({ type: 'item_start', item: { uid: 'uid-ws-1', kind: 'web_search', query: 'latest news' } }) +
    e({ type: 'item_done', item: { uid: 'uid-ws-1', kind: 'web_search', query: 'latest news', result_snippet: 'Top news results...', status: 'done' } }) +
    e({ type: 'item_start', item: { uid: 'uid-kb-1', kind: 'kb_search', query: 'news' } }) +
    e({ type: 'item_done', item: { uid: 'uid-kb-1', kind: 'kb_search', query: 'news', sources: [], status: 'done' } }) +
    e({ type: 'delta', text: 'Here is the latest news based on my web search.' }) +
    e({ type: 'done', message_id: messageId })
  )
}

const STREAM_ITEMS = [
  { uid: 'uid-mem-1', kind: 'memory', count: 1, status: 'done' },
  { uid: 'uid-ws-1', kind: 'web_search', query: 'latest news', result_snippet: 'Top news results...', status: 'done' },
  { uid: 'uid-kb-1', kind: 'kb_search', query: 'news', sources: [], status: 'done' },
]

async function setupSseAndMessages(
  page: import('@playwright/test').Page,
  convId: number,
  messageId: number,
) {
  await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: buildToolStreamSse(messageId),
    })
  })

  // Mock the messages refetch after stream ends so PersistedStreamItems shows chips
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
            content: 'Here is the latest news based on my web search.',
            created_at: new Date().toISOString(),
            extra: { stream_items: STREAM_ITEMS },
          },
        ]),
      })
    } else {
      await route.continue()
    }
  })
}

test.describe('Thread item chips UI', () => {
  test('all three item chips are visible after stream ends', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const messageId = convId * 100
    await setupSseAndMessages(page, convId, messageId)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const chips = page.getByTestId('thread-item-chip')
    await expect(chips).toHaveCount(3)
  })

  test('memory chip is non-expandable', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const messageId = convId * 100
    await setupSseAndMessages(page, convId, messageId)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('test')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const memChip = page.locator('[data-testid="thread-item-chip"][data-kind="memory"]')
    await expect(memChip).toBeVisible()
    await expect(memChip).toHaveAttribute('data-status', 'done')
    await expect(memChip.getByTestId('thread-item-chip-toggle')).toBeHidden()
  })

  test('web_search chip is expandable and shows query in details', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    const messageId = convId * 100
    await setupSseAndMessages(page, convId, messageId)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('test')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const wsChip = page.locator('[data-testid="thread-item-chip"][data-kind="web_search"]')
    await expect(wsChip).toBeVisible()
    await expect(wsChip).toHaveAttribute('data-status', 'done')

    await wsChip.getByTestId('thread-item-chip-toggle').click()
    await expect(wsChip.locator('[data-testid="thread-item-details"]')).toBeVisible()
    await expect(wsChip.locator('[data-testid="thread-item-details"]')).toContainText('latest news')
  })

  test('no item chips for plain text reply', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)

    const plainSse =
      'data: {"type":"delta","text":"Hello!"}\n\n' +
      'data: {"type":"done","message_id":999}\n\n'

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: plainSse,
      })
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('Say hello')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })
    await expect(page.getByTestId('thread-item-chip')).toHaveCount(0)
  })
})
