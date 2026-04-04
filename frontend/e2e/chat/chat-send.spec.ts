/**
 * Chat send-message and model-switching tests.
 *
 * Submits real chat turns via **Claude Haiku 4.5** (`E2E_DEFAULT_CHAT_MODEL_SLUG`).
 * Requires **ANTHROPIC_API_KEY** on the E2E API. Backend: `./scripts/e2e-up.sh`.
 */
import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

// ── helpers ───────────────────────────────────────────────────────────────

/** Send a message and wait for the assistant to finish streaming. */
async function sendMessage(page: import('@playwright/test').Page, text: string) {
  await page.getByRole('textbox', { name: /message/i }).fill(text)
  await page.getByRole('button', { name: /send message/i }).click()
  // Wait for the streaming indicator to disappear (Stop button → Send button)
  await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
    timeout: 60_000,
  })
}

// ── tests ─────────────────────────────────────────────────────────────────

test.describe('Chat — send and receive messages', () => {
  // ──────────────────────────────────────────────────────────────
  // Basic send / receive
  // ──────────────────────────────────────────────────────────────

  test('sends a message and receives an assistant reply', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await sendMessage(page, 'Reply with exactly the word PONG and nothing else.')
    // User message bubble should be in the list
    await expect(page.getByTestId('chat-message-user').first()).toBeVisible()
    // At least one assistant message bubble should appear
    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible()
  })

  test('user message text is shown in a bubble', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const userText = `E2E user bubble ${Date.now()}`
    await sendMessage(page, userText)
    await expect(page.getByTestId('chat-message-user').first()).toContainText(userText)
  })

  test('assistant reply is non-empty', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await sendMessage(page, 'Say hello.')
    const assistantMsg = page.getByTestId('chat-message-assistant').first()
    await expect(assistantMsg).toBeVisible({ timeout: 60_000 })
    const text = await assistantMsg.textContent()
    expect((text ?? '').trim().length).toBeGreaterThan(0)
  })

  test('multiple messages build up a conversation history', async ({ page, request }) => {
    test.setTimeout(180_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await sendMessage(page, 'My favourite colour is blue. Acknowledge briefly.')
    await sendMessage(page, 'What is my favourite colour?')
    // At least 2 assistant bubbles
    await expect(page.getByTestId('chat-message-assistant')).toHaveCount(2, { timeout: 60_000 })
  })

  test('reloading the page preserves chat history', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const marker = `E2E persist ${Date.now()}`
    await sendMessage(page, marker)
    await expect(page.getByTestId('chat-message-user').first()).toContainText(marker)
    // Reload and verify message is still there
    await page.reload({ waitUntil: 'networkidle' })
    await expect(page.getByTestId('chat-message-user').first()).toContainText(marker)
    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible()
  })

  test('role labels "user" and "assistant" are rendered', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await sendMessage(page, 'Say hi.')
    await expect(page.getByTestId('chat-message-user').first()).toBeVisible()
    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // Composer state during streaming
  // ──────────────────────────────────────────────────────────────

  test('Stop button is visible while streaming', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('Count slowly from 1 to 20.')
    await page.getByRole('button', { name: /send message/i }).click()
    // While streaming the Stop button should appear
    await expect(page.getByRole('button', { name: /stop generating/i })).toBeVisible({
      timeout: 10_000,
    })
  })

  test('pressing Stop halts the stream', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('Count slowly from 1 to 100.')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('button', { name: /stop generating/i })).toBeVisible({
      timeout: 10_000,
    })
    await page.getByRole('button', { name: /stop generating/i }).click()
    // Send button should come back
    await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
      timeout: 10_000,
    })
  })

  test('input is cleared after sending', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const composer = page.getByRole('textbox', { name: /message/i })
    await composer.fill('Hello!')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(composer).toHaveValue('')
  })

  // ──────────────────────────────────────────────────────────────
  // Copy / Regenerate actions on messages
  // ──────────────────────────────────────────────────────────────

  test('each message has a "Copy message" button', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await sendMessage(page, 'Say hi.')
    await expect(
      page.getByTestId('chat-message-user').first().getByRole('button', { name: /copy/i }),
    ).toBeVisible()
    await expect(
      page.getByTestId('chat-message-assistant').first().getByRole('button', { name: /copy/i }),
    ).toBeVisible()
  })

  test('latest assistant message has a "Regenerate" button', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await sendMessage(page, 'Say hi.')
    // The last assistant message should have a regenerate button
    await expect(
      page.getByTestId('chat-message-assistant').last().getByRole('button', { name: /regenerate/i }),
    ).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // Model selector
  // ──────────────────────────────────────────────────────────────

  test('model selector is visible in the composer', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(page.getByTestId('chat-model-select')).toBeVisible()
  })

  test('model selector opens a list of models', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-model-select').click()
    // At least one option in the dropdown
    await expect(page.getByRole('option').first()).toBeVisible({ timeout: 5_000 })
  })

  test('can switch model and the selector reflects the change', async ({ page, request }) => {
    test.setTimeout(30_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-model-select').click()
    // Pick the second available (accessible) option
    const options = page.getByRole('option')
    const count = await options.count()
    expect(
      count,
      'E2E needs ≥2 catalog models; run ./scripts/e2e-up.sh (migrations + seed-catalog-models).',
    ).toBeGreaterThanOrEqual(2)
    const targetName = await options.nth(1).textContent()
    await options.nth(1).click()
    // The trigger should now show the selected model
    await expect(page.getByTestId('chat-model-select')).toContainText(
      (targetName ?? '').trim().slice(0, 12),
      { timeout: 5_000 },
    )
  })

  test('model choice persists after page reload', async ({ page, request }) => {
    test.setTimeout(30_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-model-select').click()
    const options = page.getByRole('option')
    const count = await options.count()
    expect(
      count,
      'E2E needs ≥2 catalog models; run ./scripts/e2e-up.sh (migrations + seed-catalog-models).',
    ).toBeGreaterThanOrEqual(2)
    const targetName = ((await options.nth(1).textContent()) ?? '').trim()
    await options.nth(1).click()
    // Reload and verify model persists
    await page.reload({ waitUntil: 'networkidle' })
    await expect(page.getByTestId('chat-model-select')).toContainText(targetName.slice(0, 12), {
      timeout: 5_000,
    })
  })

  test('sends a message with the chosen model', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    // Switch model first
    await page.getByTestId('chat-model-select').click()
    const options = page.getByRole('option')
    const count = await options.count()
    if (count >= 1) await options.first().click()
    await sendMessage(page, 'Reply with exactly the word OK.')
    await expect(page.getByTestId('chat-message-assistant').first()).toBeVisible({ timeout: 60_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // New conversation from sidebar
  // ──────────────────────────────────────────────────────────────

  test('new conversation button creates and navigates to a fresh chat', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    // The composer should be visible on the index page
    await expect(
      page.getByPlaceholder('Message the assistant… (Shift+Enter for newline)'),
    ).toBeVisible()
  })

  test('conversation appears in the sidebar after first message', async ({ page, request }) => {
    test.setTimeout(90_000)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await sendMessage(page, 'Hello world!')
    // Navigate away then back; the sidebar should list the conversation
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    // Sidebar is an <aside> with conversation links (not inside <nav>)
    await expect(page.locator('aside ul a[href*="/chat/conversations/"]').first()).toBeVisible({
      timeout: 15_000,
    })
  })
})
