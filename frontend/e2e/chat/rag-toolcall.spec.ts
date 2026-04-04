import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'
import {
  attachKnowledgeBasesToConversation,
  createKnowledgeBase,
  seedRagToolCallForE2e,
} from '../support/knowledge-api'

test.describe('RAG tool-call UI', () => {
  test('KB indicator popover shows after seeded tool-call response', async ({ page, request }) => {
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

    const kbTrigger = page.getByTestId('message-kb-indicator-trigger')
    await expect(kbTrigger).toBeVisible({ timeout: 10_000 })
    await kbTrigger.click()

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
      .fill('What does this knowledge base contain? Answer briefly.')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByText(/searching knowledge bases/i)).toBeVisible({ timeout: 60_000 })
    await expect(page.getByText(/searching knowledge bases/i)).not.toBeVisible({ timeout: 90_000 })
  })
})
