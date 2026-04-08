import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'
import {
  attachKnowledgeBasesToConversation,
  createKnowledgeBase,
} from '../support/knowledge-api'

test.describe('Chat RAG indicator', () => {
  test('KB indicator appears when assistant uses search_knowledge_base tool', async ({
    page,
    request,
  }) => {
    test.setTimeout(60_000)
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = `E2E RAG KB ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])

    // Mock the SSE stream to return a tool-call response that includes used_kbs
    const mockMessageId = convId * 100
    const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
    const sseBody =
      e({ type: 'item_start', item: { kind: 'thinking' } }) +
      e({ type: 'item_start', item: { kind: 'tool_call', tool: 'search_knowledge_base', params: { query: 'test', kb_ids: [kbId] } } }) +
      e({ type: 'item_done', item: { kind: 'tool_call', tool: 'search_knowledge_base', status: 'done' } }) +
      e({ type: 'item_done', item: { kind: 'thinking' } }) +
      e({ type: 'delta', text: 'Grounded answer from knowledge base.' }) +
      e({ type: 'done', message_id: mockMessageId })

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'X-Accel-Buffering': 'no',
        },
        body: sseBody,
      })
    })

    // Mock the messages re-fetch to return a message with used_kbs
    await page.route(`**/api/chat/conversations/${convId}/messages**`, async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([
          {
            id: mockMessageId,
            conversation_id: convId,
            role: 'assistant',
            content: 'Grounded answer from knowledge base.',
            created_at: new Date().toISOString(),
            extra: null,
            used_kbs: [
              {
                kb_id: kbId,
                kb_name: kbName,
                chunks_used: 2,
                top_score: 0.9,
              },
            ],
          },
        ]),
      })
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('What does the KB say?')
    await page.getByRole('button', { name: /send message/i }).click()

    // After stream ends, messages are re-fetched; KB indicator should appear
    const kbTriggers = page.getByTestId('message-kb-indicator-trigger')
    await expect(kbTriggers).toHaveCount(1, { timeout: 20_000 })
    await kbTriggers.hover()
    const popover = page.getByTestId('message-kb-indicator-popover')
    await expect(popover).toBeVisible()
    await expect(popover.getByText(kbName, { exact: false })).toBeVisible()
  })
})
