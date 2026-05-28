/**
 * Cross-module: memory recall.
 *
 * Covers:
 *  - Send a turn in conversation A.
 *  - Start a new conversation B.
 *  - Memory recall surfaces in the new turn's memory sidebar.
 *
 * Memory write + recall are both browser-mocked via page.route().
 */
import { test, expect } from '@playwright/test'

import { createOrFindConversation } from '../support/ui-helpers'

const STREAM_ROUTE = '**/api/chat/conversations/*/messages/stream'
const MESSAGES_ROUTE = '**/api/chat/conversations/*/messages*'
const MEMORIES_ROUTE = '**/api/users/me/memories**'
const RECALL_ROUTE = '**/api/memories/recall**'

function mockTurn(page: import('@playwright/test').Page, userText: string, assistantText: string) {
  const turnId = `00000000-0000-4000-8000-${String(Date.now()).slice(-12)}`
  const assistantItem = {
    id: 5001,
    thread_id: 9999,
    turn_id: turnId,
    kind: 'assistant_text',
    role: 'assistant',
    status: 'done',
    provider: null,
    model: null,
    cost_usd: null,
    cost_estimated: false,
    latency_ms: null,
    data: { text: assistantText },
    parent_item_id: null,
    started_at: null,
    finished_at: null,
    created_at: new Date().toISOString(),
  }
  page.route(STREAM_ROUTE, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        `data: ${JSON.stringify({ event_type: 'item', item: assistantItem })}\n\n`,
        'data: {"event_type":"done"}\n\n',
      ].join(''),
    })
  })
  page.route(MESSAGES_ROUTE, async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 5000,
          thread_id: 9999,
          turn_id: turnId,
          kind: 'user_message',
          role: 'user',
          status: 'done',
          provider: null,
          model: null,
          cost_usd: null,
          cost_estimated: false,
          latency_ms: null,
          data: { text: userText, attachments: [] },
          parent_item_id: null,
          started_at: null,
          finished_at: null,
          created_at: new Date().toISOString(),
        },
        assistantItem,
      ]),
    })
  })
}

test.describe('Suite — Memory', () => {
  test('memory recall surfaces in a new conversation sidebar', async ({ page }) => {
    test.setTimeout(120_000)

    const MEMORY_CONTENT = `User prefers concise answers ${Date.now()}`

    // Mock memories list — after the first turn the memory should "exist".
    let memoryWritten = false
    await page.route(MEMORIES_ROUTE, async (route) => {
      if (route.request().method() === 'POST') {
        memoryWritten = true
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 7777,
            content: MEMORY_CONTENT,
            created_at: new Date().toISOString(),
          }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          memoryWritten
            ? [{ id: 7777, content: MEMORY_CONTENT, created_at: new Date().toISOString() }]
            : [],
        ),
      })
    })

    // Mock recall — returns the memory once it was "written".
    await page.route(RECALL_ROUTE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: memoryWritten
            ? [{ id: 7777, content: MEMORY_CONTENT, score: 0.88 }]
            : [],
        }),
      })
    })

    // 1. Conversation A — send a turn that should generate a memory.
    await createOrFindConversation(page, 'E2E Memory Source A')
    mockTurn(page, 'Please be concise from now on.', 'Got it — I will be concise.')
    await page.getByRole('textbox', { name: /message/i }).fill('Please be concise from now on.')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
      timeout: 60_000,
    })

    // Simulate the memory extractor having written the memory.
    await page.evaluate(async (content) => {
      await fetch('/api/users/me/memories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer devtoken' },
        body: JSON.stringify({ content }),
      })
    }, MEMORY_CONTENT)

    // 2. Conversation B — start a new conversation.
    await page.unroute(STREAM_ROUTE)
    await page.unroute(MESSAGES_ROUTE)
    await createOrFindConversation(page, `E2E Memory Target B ${Date.now()}`)
    mockTurn(page, 'Summarise our chat.', 'Short summary.')
    await page.getByRole('textbox', { name: /message/i }).fill('Summarise our chat.')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
      timeout: 60_000,
    })

    // 3. Memory sidebar should surface the recalled memory.
    //    Surface uses one of: data-testid="memory-sidebar", "memory-recall-list", "memory-chip".
    const sidebar = page
      .getByTestId('memory-sidebar')
      .or(page.getByTestId('memory-recall-list'))
      .or(page.getByRole('region', { name: /memor/i }))
      .first()
    await expect(sidebar).toBeVisible({ timeout: 15_000 })
    await expect(sidebar.getByText(MEMORY_CONTENT)).toBeVisible({ timeout: 10_000 })
  })
})
