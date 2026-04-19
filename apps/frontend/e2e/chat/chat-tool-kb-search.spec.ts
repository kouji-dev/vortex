import { test, expect } from '@playwright/test'
import { createOrFindConversation, createOrFindKb, attachKbToConversationViaUi } from '../support/ui-helpers'

test.describe.configure({ mode: 'serial' })

const CONV_NAME = 'E2E KB Search Tool'
const KB_NAME = 'E2E KB Search Fixture'

function buildKbSearchSse(messageId: number, kbId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { uid: 'uid-kb-1', kind: 'kb_search', query: 'project summary' } }) +
    e({ type: 'item_done', item: { uid: 'uid-kb-1', kind: 'kb_search', query: 'project summary', sources: [{ kb_name: 'Test KB', chunks_used: 2 }], status: 'done' } }) +
    e({ type: 'delta', text: 'Based on your documents, the project summary is...' }) +
    e({ type: 'done', message_id: messageId })
  )
}

test.describe('kb_search tool', () => {
  test('Test A — KB tool card renders during stream', async ({ page }) => {
    const kbId = await createOrFindKb(page, KB_NAME)
    const convId = await createOrFindConversation(page, CONV_NAME)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await attachKbToConversationViaUi(page, KB_NAME)

    const messageId = convId * 1000 + 10
    const sseBody = buildKbSearchSse(messageId, kbId)

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      })
    })

    // Mock messages refetch so PersistedStreamItems shows chips after stream ends
    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: messageId,
              conversation_id: convId,
              role: 'assistant',
              content: 'Based on your documents, the project summary is...',
              created_at: new Date().toISOString(),
              extra: {
                stream_items: [
                  { uid: 'uid-kb-1', kind: 'kb_search', query: 'project summary', sources: [{ kb_name: 'Test KB', chunks_used: 2 }], status: 'done' },
                ],
              },
            },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    const textarea = page.getByRole('textbox', { name: /message/i })
    await textarea.fill('Summarise the project')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const kbChip = page.locator('[data-testid="thread-item-chip"][data-kind="kb_search"]')
    await expect(kbChip).toBeVisible()
    await expect(kbChip).toHaveAttribute('data-status', 'done')

    await kbChip.getByTestId('thread-item-chip-toggle').click()
    const details = kbChip.locator('[data-testid="thread-item-details"]')
    await expect(details).toBeVisible()
    await expect(details).toContainText('project summary')
  })

  test('Test B — KB indicator on assistant message', async ({ page }) => {
    const kbId = await createOrFindKb(page, KB_NAME)
    const convId = await createOrFindConversation(page, CONV_NAME)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await attachKbToConversationViaUi(page, KB_NAME)

    const messageId = convId * 1000 + 11
    const sseBody = buildKbSearchSse(messageId, kbId)
    let streamCompleted = false

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      })
      streamCompleted = true
    })

    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET' && streamCompleted) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: messageId,
              conversation_id: convId,
              role: 'assistant',
              content: 'Based on your documents, the project summary is...',
              created_at: new Date().toISOString(),
              extra: {
                used_kbs: [
                  {
                    kb_id: kbId,
                    kb_name: KB_NAME,
                    chunks_used: 2,
                    top_score: 0.85,
                    sections: ['Introduction'],
                  },
                ],
              },
            },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    await page.getByRole('textbox', { name: /message/i }).fill('Summarise the project')
    await page.getByRole('button', { name: /send message/i }).click()

    // Wait for stream to finish
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    // Assistant message is present
    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg).toContainText('Based on your documents')

    // KB indicator trigger is visible on the assistant message
    await expect(assistantMsg.getByTestId('message-kb-indicator-trigger')).toBeVisible()
  })
})
