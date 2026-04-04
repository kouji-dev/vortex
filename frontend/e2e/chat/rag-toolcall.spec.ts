import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'
import {
  attachKnowledgeBasesToConversation,
  createKnowledgeBase,
  seedRagToolCallForE2e,
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

    const seedStatus = await seedRagToolCallForE2e(request, apiBase, convId, kbId, kbName)
    expect(
      seedStatus,
      'e2e/seed-rag-assistant must return 201 (./scripts/e2e-up.sh sets E2E_ENABLE_RAG_SEED=1).',
    ).toBe(201)

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

  test('"Searching knowledge bases" indicator appears during tool-call stream', async ({
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

    const searching = page.getByTestId('chat-stream-kb-searching')
    const assistant = page.getByTestId('chat-message-assistant').last()
    const sawSearching = await searching
      .waitFor({ state: 'visible', timeout: 90_000 })
      .then(() => true)
      .catch(() => false)
    if (sawSearching) {
      await expect(searching).toBeHidden({ timeout: 90_000 })
    } else {
      await expect(assistant).toBeVisible({ timeout: 90_000 })
      await expect(assistant).not.toContainText('**Error:**')
    }
  })
})
