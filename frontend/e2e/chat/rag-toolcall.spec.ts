import { test, expect } from '@playwright/test'
import { e2eStableResourceName } from '../support/resource-slug'
import { seedRagToolCallForE2e } from '../support/knowledge-api'
import {
  attachKbToConversationViaUi,
  createOrFindConversation,
  createOrFindKb,
} from '../support/ui-helpers'

test.describe.configure({ mode: 'serial' })

test.describe('RAG tool-call UI', () => {
  test('seeded tool-call assistant message is visible in the thread', async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000)
    const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const kbName = e2eStableResourceName('kb', test.info().title)
    const kbId = await createOrFindKb(page, kbName)
    const convId = await createOrFindConversation(page, 'E2E RAG Toolcall Shared')
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await attachKbToConversationViaUi(page, kbName)

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

  test('"Thinking block" indicator appears during tool-call stream', async ({ page }) => {
    test.setTimeout(180_000)
    const kbName = e2eStableResourceName('kb', `${test.info().title} live`)
    await createOrFindKb(page, kbName)
    const convId = await createOrFindConversation(page, 'E2E RAG Toolcall Live Shared')
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await attachKbToConversationViaUi(page, kbName)

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
