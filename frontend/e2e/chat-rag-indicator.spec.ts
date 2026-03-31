import { test, expect } from '@playwright/test'

import { createEmptyConversation } from './helpers/create-conversation'
import {
  attachKnowledgeBasesToConversation,
  createKnowledgeBase,
  seedRagAssistantForE2e,
} from './helpers/knowledge-api'

test.describe('Chat RAG KB indicator', () => {
  test('only assistant message with used_kbs shows the KB control', async ({
    page,
    request,
  }) => {
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = `E2E RAG KB ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])

    const seedStatus = await seedRagAssistantForE2e(request, apiBase, convId, kbId, kbName)
    if (seedStatus === 404) {
      test.skip(
        true,
        'Start the API with E2E_ENABLE_RAG_SEED=1 (dev auth) to enable the RAG indicator seed endpoint.',
      )
      return
    }
    expect(seedStatus).toBe(201)

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await expect(page.getByText('A short reply without retrieval metadata.')).toBeVisible()
    await expect(
      page.getByText('Grounded answer from E2E seed', { exact: false }),
    ).toBeVisible()

    const kbTriggers = page.getByTestId('message-kb-indicator-trigger')
    await expect(kbTriggers).toHaveCount(1)

    await kbTriggers.click()
    await expect(page.getByTestId('message-kb-indicator-popover')).toBeVisible()
    await expect(page.getByText(kbName, { exact: false }).first()).toBeVisible()
    await expect(page.getByText(/chunks/i).first()).toBeVisible()
  })
})
