import { test, expect } from '@playwright/test'
import { createEmptyConversation } from './helpers/create-conversation'
import {
  attachKnowledgeBasesToConversation,
  createKnowledgeBase,
  seedRagToolCallForE2e,
} from './helpers/knowledge-api'

test.describe('RAG tool-call UI', () => {
  test('KB indicator popover shows after seeded tool-call response', async ({ page, request }) => {
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = `E2E ToolCall KB ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])

    const seedStatus = await seedRagToolCallForE2e(request, apiBase, convId, kbId, kbName)
    if (seedStatus === 404) {
      test.skip(true, 'Start the API with E2E_ENABLE_RAG_SEED=1 to run this test.')
      return
    }
    expect(seedStatus).toBe(201)

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    // KB indicator should appear on the seeded assistant message
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
    test.skip(
      process.env.E2E_REQUIRE_LIVE_STREAM !== '1',
      'Set E2E_REQUIRE_LIVE_STREAM=1 with a working LLM API key to test the live streaming indicator.',
    )

    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = `E2E Live Stream KB ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox').fill('What does this knowledge base contain?')
    await page.keyboard.press('Enter')

    // The "Searching knowledge bases…" text should appear transiently when the model emits a tool call
    await expect(page.getByText(/searching knowledge bases/i)).toBeVisible({ timeout: 15_000 })
    // Then disappear when streaming completes
    await expect(page.getByText(/searching knowledge bases/i)).not.toBeVisible({ timeout: 30_000 })
  })
})
