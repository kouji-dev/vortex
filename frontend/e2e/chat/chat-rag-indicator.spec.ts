import { test, expect } from '@playwright/test'

import { e2eStableResourceName } from '../support/resource-slug'
import { seedRagAssistantForE2e } from '../support/knowledge-api'
import {
  attachKbToConversationViaUi,
  createOrFindConversation,
  createOrFindKb,
} from '../support/ui-helpers'

test.describe('Chat RAG seeded messages', () => {
  test('seeded thread shows both assistant replies (with and without used_kbs)', async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000)
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = e2eStableResourceName('kb', test.info().title)
    const kbId = await createOrFindKb(page, kbName)
    const convId = await createOrFindConversation(page, 'E2E RAG Indicator Shared')
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await attachKbToConversationViaUi(page, kbName)

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
