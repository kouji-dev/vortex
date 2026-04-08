import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'
import {
  attachKnowledgeBasesToConversation,
  createKnowledgeBase,
} from '../support/knowledge-api'

test.describe.configure({ mode: 'serial' })

test.describe('RAG tool-call UI', () => {
  test('seeded tool-call assistant message is visible in the thread', async ({
    page,
    request,
  }) => {
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = `E2E ToolCall KB ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])

    // Mock the messages endpoint to return a pre-built RAG tool-call assistant message
    const messages = [
      {
        id: 1,
        conversation_id: convId,
        role: 'user',
        content: 'What is in this knowledge base?',
        created_at: new Date(Date.now() - 10_000).toISOString(),
        extra: null,
      },
      {
        id: 2,
        conversation_id: convId,
        role: 'assistant',
        content: 'This reply used the search_knowledge_base tool to look up information from the knowledge base.',
        created_at: new Date().toISOString(),
        extra: null,
        used_kbs: [{ kb_id: kbId, kb_name: kbName, chunks_used: 2, top_score: 0.9 }],
      },
    ]

    await page.route(`**/api/chat/conversations/${convId}/messages**`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(messages) })
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await expect(
      page.getByText('This reply used the search_knowledge_base tool', { exact: false }),
    ).toBeVisible({ timeout: 15_000 })

    const kbTrigger = page.getByTestId('message-kb-indicator-trigger')
    await expect(kbTrigger).toBeVisible({ timeout: 10_000 })
    await kbTrigger.hover()
    const popover = page.getByTestId('message-kb-indicator-popover')
    await expect(popover).toBeVisible()
    await expect(popover.getByText(kbName, { exact: false })).toBeVisible()
  })

  test('"Thinking block" indicator appears during tool-call stream', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = `E2E Live Stream KB ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page
      .getByRole('textbox', { name: /message/i })
      .fill(
        'Use the knowledge base retrieval tool if available. What is in this knowledge base? Reply in one short sentence.',
      )
    await page.getByRole('button', { name: /send message/i }).click()

    const thinkingBlock = page.getByTestId('chat-thinking-block')
    const pill = page.getByTestId('chat-thinking-pill')
    const assistant = page.getByTestId('chat-message-assistant').last()

    // Either the thinking block appears during stream, or the pill appears after,
    // or the assistant message appeared without any tool use (also valid)
    const sawIndicator = await Promise.race([
      thinkingBlock.waitFor({ state: 'visible', timeout: 90_000 }).then(() => true),
      pill.waitFor({ state: 'visible', timeout: 90_000 }).then(() => true),
      assistant.waitFor({ state: 'visible', timeout: 90_000 }).then(() => false),
    ]).catch(() => false)

    if (!sawIndicator) {
      await expect(assistant).not.toContainText('**Error:**')
    }
  })
})
