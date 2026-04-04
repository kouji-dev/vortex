/**
 * Chat attachments — upload API, stream payload check, and LLM reads file content.
 *
 * Conversations use **Claude Haiku 4.5** via `createEmptyConversation` (needs
 * **ANTHROPIC_API_KEY** on the API). Requires migration `020_chat_conversation_uploads`.
 * Run `./scripts/e2e-up.sh` or `./scripts/e2e-db-sync.sh` before the API.
 *
 * @see docs/superpowers/specs/2026-04-04-chat-remaining-features-delivery.md
 */
import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

test.describe('Chat attachments API', () => {
  test('POST uploads returns 201 for .txt', async ({ request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    const res = await request.post(
      `${apiBase.replace(/\/$/, '')}/api/chat/conversations/${convId}/uploads`,
      {
        headers: { Authorization: 'Bearer devtoken' },
        multipart: {
          file: {
            name: 'e2e-note.txt',
            mimeType: 'text/plain',
            buffer: Buffer.from('e2e attachment body'),
          },
        },
      },
    )
    expect(res.status(), await res.text()).toBe(201)
    const body = (await res.json()) as { id: number; original_filename: string; size_bytes: number }
    expect(body.id).toBeGreaterThan(0)
    expect(body.original_filename).toContain('e2e-note')
    expect(body.size_bytes).toBeGreaterThan(0)
  })
})

test.describe('Chat attachments — stream request', () => {
  test('after attach, first messages/stream POST includes attachment_ids', async ({
    page,
    request,
  }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)

    const streamWait = page.waitForRequest(
      (r) => r.url().includes('/messages/stream') && r.method() === 'POST',
      { timeout: 75_000 },
    )

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-add-options').click()
    await page.getByRole('menuitem', { name: /attach text file/i }).click()
    await page.locator('input[type="file"][accept=".txt,.md,text/plain"]').setInputFiles({
      name: 'stream-payload.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Stream payload check: file is attached to this turn.'),
    })
    await expect(page.getByRole('list', { name: /attachments to send/i })).toBeVisible({
      timeout: 20_000,
    })
    await expect(page.getByRole('list', { name: /attachments to send/i })).toContainText(
      'stream-payload.txt',
    )

    await page
      .getByRole('textbox', { name: /message/i })
      .fill('Reply briefly; this message exists to carry attachment_ids in the request body.')
    await page.getByRole('button', { name: /send message/i }).click()

    const req = await streamWait
    const raw = req.postData()
    expect(raw, 'stream POST should have JSON body').toBeTruthy()
    const body = JSON.parse(raw!) as { attachment_ids?: number[]; content?: string }
    expect(Array.isArray(body.attachment_ids), JSON.stringify(body)).toBe(true)
    expect(body.attachment_ids!.length).toBeGreaterThan(0)
    expect(body.attachment_ids![0]).toBeGreaterThan(0)
    expect((body.content ?? '').trim().length).toBeGreaterThan(0)
  })
})

test.describe('Chat attachments — assistant uses file (Claude Haiku)', () => {
  test('assistant answer reflects unique text inside the attached file', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)
    const convId = await createEmptyConversation(request, apiBase)

    const secret = `E2E_FILE_SECRET_${Date.now()}`
    const fileBody = `Confidential line for automated testing.\nThe secret codeword is exactly: ${secret}\nEnd of file.\n`

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-add-options').click()
    await page.getByRole('menuitem', { name: /attach text file/i }).click()
    await page.locator('input[type="file"][accept=".txt,.md,text/plain"]').setInputFiles({
      name: 'secret-e2e.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from(fileBody),
    })
    await expect(page.getByRole('list', { name: /attachments to send/i })).toBeVisible({
      timeout: 20_000,
    })

    await page.getByRole('textbox', { name: /message/i }).fill(
      'Read ONLY the attached text file. What is the secret codeword on the line that starts with "The secret codeword is exactly:"? Reply with only that codeword (one token, same spelling), no quotes or punctuation.',
    )
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible({
      timeout: 90_000,
    })
    await expect(page.getByTestId('chat-message-assistant').first()).toContainText(secret, {
      timeout: 15_000,
    })
  })
})
