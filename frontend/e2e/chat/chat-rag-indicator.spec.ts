import { test, expect } from '@playwright/test'

import { createEmptyConversation } from '../support/create-conversation'
import {
  attachKnowledgeBasesToConversation,
  createKnowledgeBase,
  seedRagAssistantForE2e,
} from '../support/knowledge-api'

test.describe('Chat RAG seeded messages', () => {
  test('seeded thread shows both assistant replies (with and without used_kbs)', async ({
    page,
    request,
  }) => {
    test.setTimeout(90_000)
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = `E2E RAG KB ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])

    const seedStatus = await seedRagAssistantForE2e(request, apiBase, convId, kbId, kbName)
    expect(
      seedStatus,
      'e2e/seed-rag-assistant must return 201 (./scripts/e2e-up.sh sets E2E_ENABLE_RAG_SEED=1).',
    ).toBe(201)

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await expect(page.getByText('A short reply without retrieval metadata.')).toBeVisible({
      timeout: 20_000,
    })
    await expect(
      page.getByText('Grounded answer from E2E seed', { exact: false }),
    ).toBeVisible()

    const kbTriggers = page.getByTestId('message-kb-indicator-trigger')
    await expect(kbTriggers).toHaveCount(1)
    await kbTriggers.hover()
    const popover = page.getByTestId('message-kb-indicator-popover')
    await expect(popover).toBeVisible()
    await expect(popover.getByText(kbName, { exact: false })).toBeVisible()
  })
})
