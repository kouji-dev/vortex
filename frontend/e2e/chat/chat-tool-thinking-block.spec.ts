import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'
import { seedToolStream } from '../support/tool-stream-api'

test.describe.configure({ mode: 'serial' })

const apiBase = () => process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

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
    const base = apiBase()
    const convId = await createEmptyConversation(request, base)
    const { sse } = await seedToolStream(request, base, convId)

    await setupSseReplay(page, convId, sse)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    // After stream resolves: pill visible, tool cards hidden (collapsed)
    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })
    // Block container is present but tool cards are not visible when collapsed
    const toolCards = page.getByTestId('chat-tool-card')
    await expect(toolCards.first()).toBeHidden()
  })

  test('user can expand thinking block by clicking the pill', async ({ page, request }) => {
    const base = apiBase()
    const convId = await createEmptyConversation(request, base)
    const { sse } = await seedToolStream(request, base, convId)

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
    const base = apiBase()
    const convId = await createEmptyConversation(request, base)
    const { sse } = await seedToolStream(request, base, convId)

    await setupSseReplay(page, convId, sse)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })
    await pill.click()

    const block = page.getByTestId('chat-thinking-block')
    await expect(block).toBeVisible()

    // Click pill again (it's still visible in expanded state)
    await pill.click()
    // After collapse, tool cards should not be visible
    const toolCards = page.getByTestId('chat-tool-card')
    await expect(toolCards.first()).toBeHidden()
  })

  test('tool cards show correct tool names after expanding', async ({ page, request }) => {
    const base = apiBase()
    const convId = await createEmptyConversation(request, base)
    const { sse } = await seedToolStream(request, base, convId)

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
    // Seed has web_search → "Web Search" and search_knowledge_base → "Knowledge Base"
    expect(allNames.some(n => n.includes('Web Search'))).toBe(true)
  })

  test('tool cards show "done" status after stream ends', async ({ page, request }) => {
    const base = apiBase()
    const convId = await createEmptyConversation(request, base)
    const { sse } = await seedToolStream(request, base, convId)

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
    const base = apiBase()
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

    // Neither the block nor the pill should appear
    await expect(page.getByTestId('chat-thinking-block')).toBeHidden()
    await expect(page.getByTestId('chat-thinking-pill')).toBeHidden()
  })
})
