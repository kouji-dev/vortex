import { test, expect } from '@playwright/test'
import { createOrFindConversation, createOrFindKb, attachKbToConversationViaUi } from '../support/ui-helpers'

test.describe.configure({ mode: 'serial' })

const RUN_ID = Date.now()
const CONV_NAME = `E2E KB Search Tool ${RUN_ID}`
const KB_NAME = `E2E KB Search Fixture ${RUN_ID}`

function buildKbSearchSse(messageId: number, kbId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { kind: 'thinking' } }) +
    e({ type: 'item_start', item: { kind: 'tool_call', tool: 'search_knowledge_base', params: { query: 'project summary', kb_ids: [kbId] } } }) +
    e({ type: 'item_done', item: { kind: 'tool_call', tool: 'search_knowledge_base', status: 'done' } }) +
    e({ type: 'item_done', item: { kind: 'thinking' } }) +
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

    const textarea = page.getByRole('textbox', { name: /message/i })
    await textarea.fill('Summarise the project')
    await page.getByRole('button', { name: /send message/i }).click()

    // Thinking pill becomes visible once stream ends
    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })

    // Expand to see tool cards
    await pill.click()
    const block = page.getByTestId('chat-thinking-block')
    await expect(block).toBeVisible()

    // Tool card for search_knowledge_base
    const toolCard = block.getByTestId('chat-tool-card').first()
    await expect(toolCard).toBeVisible()
    await expect(toolCard.getByTestId('chat-tool-card-name')).toHaveText('Knowledge Base')

    // Param shows query
    await expect(toolCard.getByTestId('chat-tool-card-param')).toHaveText('project summary')

    // Status is done
    await expect(toolCard.getByTestId('chat-tool-card-status')).toHaveText('done')

    // Textarea re-enables
    await expect(textarea).toBeEnabled({ timeout: 15_000 })
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
