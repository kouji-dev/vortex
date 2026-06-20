/**
 * Chat send-message and model-switching tests.
 *
 * Every chat turn is mocked at the browser via `installChatStreamMock` — no real
 * LLM is ever called. Conversations are opened or created via the UI
 * (`createOrFindConversation`) with stable shared titles so rows are reused
 * across runs instead of accumulating. Backend: `./scripts/e2e-up.sh`.
 */
import { test, expect } from '../support/fixtures'
import { gotoChatComposerIndex } from '../support/conversation-ui'
import { createOrFindConversation } from '../support/ui-helpers'
import { installChatStreamMock, makeItem, newTurnId } from '../support/chat-mock'

const E2E_CHAT_SEND_SHARED = 'E2E Chat Send Shared'

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

test.describe('Chat — send and receive messages', () => {
  // ──────────────────────────────────────────────────────────────
  // Regression: user message must not disappear when stream ends
  // ──────────────────────────────────────────────────────────────

  test('user message remains visible after mocked stream ends (regression)', async ({ page }) => {
    // Use a mocked instant stream so the race window is as tight as possible.
    await page.goto('/chat/conversations', { waitUntil: 'domcontentloaded' })
    const userText = `E2E regression persist ${Date.now()}`
    const cleanup = await installChatStreamMock(page, {
      script: { userText, assistantText: 'Hello' },
    })
    try {
      await page.getByRole('textbox', { name: /message/i }).fill(userText)
      await page.getByRole('button', { name: /send message/i }).click()
      // Wait for stream to complete (Send button reappears)
      await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
        timeout: 30_000,
      })
      // Both messages must be visible after the stream ends — this is the regression check
      await expect(
        page.getByTestId('chat-message-user').filter({ hasText: userText }).first(),
      ).toBeVisible({ timeout: 5_000 })
      await expect(page.getByTestId('chat-message-assistant').last()).toBeVisible({ timeout: 5_000 })
    } finally {
      await cleanup()
    }
  })
  // ──────────────────────────────────────────────────────────────
  // Basic send / receive
  // ──────────────────────────────────────────────────────────────

  test('sends a message and receives an assistant reply', async ({ page }) => {
    test.setTimeout(30_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const cleanup = await installChatStreamMock(page, {
      script: { userText: 'Reply with exactly the word PONG and nothing else.', assistantText: 'PONG' },
    })
    try {
      await sendMessage(page, 'Reply with exactly the word PONG and nothing else.')
      await expect(page.getByTestId('chat-message-user').last()).toBeVisible()
      await expect(page.getByTestId('chat-message-assistant').last()).toBeVisible()
      await expect(page.getByTestId('chat-message-assistant').last()).toContainText('PONG')
    } finally {
      await cleanup()
    }
  })

  test('user message text is shown in a bubble', async ({ page }) => {
    test.setTimeout(30_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const userText = `E2E user bubble ${Date.now()}`
    const cleanup = await installChatStreamMock(page, { script: { userText, assistantText: 'OK' } })
    try {
      await sendMessage(page, userText)
      await expect(
        page.getByTestId('chat-message-user').filter({ hasText: userText }).first(),
      ).toBeVisible()
    } finally {
      await cleanup()
    }
  })

  test('assistant reply is non-empty', async ({ page }) => {
    test.setTimeout(30_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const cleanup = await installChatStreamMock(page, {
      script: { userText: 'Say hello.', assistantText: 'Hello!' },
    })
    try {
      await sendMessage(page, 'Say hello.')
      const assistantMsg = page.getByTestId('chat-message-assistant').last()
      await expect(assistantMsg).toBeVisible()
      const text = await assistantMsg.textContent()
      expect((text ?? '').trim().length).toBeGreaterThan(0)
    } finally {
      await cleanup()
    }
  })

  test('multiple messages build up a conversation history', async ({ page }) => {
    test.setTimeout(30_000)
    await createOrFindConversation(page, `E2E Multi Turn ${Date.now()}`)
    // First send
    const cleanup1 = await installChatStreamMock(page, {
      script: {
        userText: 'My favourite colour is blue. Acknowledge briefly.',
        assistantText: 'Got it, blue is your favourite colour.',
      },
    })
    try {
      await sendMessage(page, 'My favourite colour is blue. Acknowledge briefly.')
    } finally {
      await cleanup1()
    }
    // Second send — GET returns both turns
    const turnId1 = newTurnId()
    const turnId2 = newTurnId()
    const cleanup2 = await installChatStreamMock(page, {
      script: {
        userText: 'What is my favourite colour?',
        assistantText: 'Your favourite colour is blue.',
        turnItems: [
          makeItem('user_message', { text: 'My favourite colour is blue.', attachments: [] }, { id: 900, turnId: turnId1, role: 'user' }),
          makeItem('assistant_text', { text: 'Got it.' }, { id: 901, turnId: turnId1 }),
          makeItem('user_message', { text: 'What is my favourite colour?', attachments: [] }, { id: 902, turnId: turnId2, role: 'user' }),
          makeItem('assistant_text', { text: 'Your favourite colour is blue.' }, { id: 903, turnId: turnId2 }),
        ],
      },
    })
    try {
      await sendMessage(page, 'What is my favourite colour?')
      await expect(async () => {
        const n = await page.getByTestId('chat-message-assistant').count()
        expect(n).toBeGreaterThanOrEqual(2)
      }).toPass({ timeout: 10_000 })
    } finally {
      await cleanup2()
    }
  })

  test('reloading the page preserves chat history', async ({ page }) => {
    test.setTimeout(90_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const marker = `E2E persist ${Date.now()}`
    const cleanup = await installChatStreamMock(page, {
      script: { userText: marker, assistantText: 'Acknowledged.' },
    })
    try {
      await sendMessage(page, marker)
      await expect(
        page.getByTestId('chat-message-user').filter({ hasText: marker }).first(),
      ).toBeVisible()
      // The GET mock remains active after reload, so messages are still available.
      await page.reload({ waitUntil: 'domcontentloaded' })
      await expect(
        page.getByTestId('chat-message-user').filter({ hasText: marker }).first(),
      ).toBeVisible()
      await expect(page.getByTestId('chat-message-assistant').last()).toBeVisible()
    } finally {
      await cleanup()
    }
  })

  test('role labels "user" and "assistant" are rendered', async ({ page }) => {
    test.setTimeout(30_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const cleanup = await installChatStreamMock(page, {
      script: { userText: 'Say hi.', assistantText: 'Hi there!' },
    })
    try {
      await sendMessage(page, 'Say hi.')
      await expect(page.getByTestId('chat-message-user').last()).toBeVisible()
      await expect(page.getByTestId('chat-message-assistant').last()).toBeVisible()
    } finally {
      await cleanup()
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Composer state during streaming
  // ──────────────────────────────────────────────────────────────

  test('Stop button is visible while streaming', async ({ page }) => {
    test.setTimeout(90_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    // Keep the stream pending so the Stop button stays visible.
    const cleanup = await installChatStreamMock(page, {
      script: { assistantText: '...' },
      delayMs: 10_000,
    })
    try {
      await page.getByRole('textbox', { name: /message/i }).fill('Count slowly from 1 to 20.')
      await page.getByRole('button', { name: /send message/i }).click()
      await expect(page.getByRole('button', { name: /stop generating/i })).toBeVisible({
        timeout: 10_000,
      })
    } finally {
      await cleanup()
    }
  })

  test('pressing Stop halts the stream', async ({ page }) => {
    test.setTimeout(90_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const cleanup = await installChatStreamMock(page, {
      script: { assistantText: '...' },
      delayMs: 10_000,
    })
    try {
      await page.getByRole('textbox', { name: /message/i }).fill('Count slowly from 1 to 100.')
      await page.getByRole('button', { name: /send message/i }).click()
      await expect(page.getByRole('button', { name: /stop generating/i })).toBeVisible({
        timeout: 10_000,
      })
      await page.getByRole('button', { name: /stop generating/i }).click()
      await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
        timeout: 10_000,
      })
    } finally {
      await cleanup()
    }
  })

  test('input is cleared after sending', async ({ page }) => {
    test.setTimeout(90_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const cleanup = await installChatStreamMock(page, { script: { assistantText: 'OK' } })
    try {
      const composer = page.getByRole('textbox', { name: /message/i })
      await composer.fill('Hello!')
      await page.getByRole('button', { name: /send message/i }).click()
      await expect(composer).toHaveValue('')
    } finally {
      await cleanup()
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Copy / Regenerate actions on messages
  // ──────────────────────────────────────────────────────────────

  test('each message has a "Copy message" button', async ({ page }) => {
    test.setTimeout(30_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const cleanup = await installChatStreamMock(page, {
      script: { userText: 'Say hi.', assistantText: 'Hello there!' },
    })
    try {
      await sendMessage(page, 'Say hi.')
      await expect(
        page.getByTestId('chat-message-user').last().getByRole('button', { name: /copy/i }),
      ).toBeVisible()
      await expect(
        page.getByTestId('chat-message-assistant').last().getByRole('button', { name: /copy/i }),
      ).toBeVisible()
    } finally {
      await cleanup()
    }
  })

  test('latest assistant message has a "Regenerate" button', async ({ page }) => {
    test.setTimeout(30_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const cleanup = await installChatStreamMock(page, {
      script: { userText: 'Say hi.', assistantText: 'Hello there!' },
    })
    try {
      await sendMessage(page, 'Say hi.')
      await expect(
        page.getByTestId('chat-message-assistant').last().getByRole('button', { name: /regenerate/i }),
      ).toBeVisible()
    } finally {
      await cleanup()
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Model selector
  // ──────────────────────────────────────────────────────────────

  test('model selector is visible in the composer', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await expect(page.getByTestId('chat-model-select')).toBeVisible()
  })

  test('model selector opens a list of models', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-model-select').click()
    await expect(page.getByRole('option').first()).toBeVisible({ timeout: 5_000 })
  })

  test('can switch model and the selector reflects the change', async ({ page }) => {
    test.setTimeout(30_000)
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-model-select').click()
    const options = page.getByRole('option')
    const count = await options.count()
    expect(
      count,
      'E2E needs ≥2 catalog models; run ./scripts/e2e-up.sh (migrations + seed-catalog-models).',
    ).toBeGreaterThanOrEqual(2)
    const targetName = await options.nth(1).textContent()
    await options.nth(1).click()
    await expect(page.getByTestId('chat-model-select')).toContainText(
      (targetName ?? '').trim().slice(0, 12),
      { timeout: 5_000 },
    )
  })

  test('model choice persists after page reload', async ({ page }) => {
    // Must use a persisted thread (thread mode) — composer mode model is not persisted across reloads.
    // Use a unique conversation so parallel workers don't PATCH the model concurrently.
    test.setTimeout(60_000)
    const convId = await createOrFindConversation(page, `E2E Model Persist ${Date.now()}`)
    await page.getByTestId('chat-model-select').click()
    const options = page.getByRole('option')
    const count = await options.count()
    expect(
      count,
      'E2E needs ≥2 catalog models; run ./scripts/e2e-up.sh (migrations + seed-catalog-models).',
    ).toBeGreaterThanOrEqual(2)
    const targetName = ((await options.nth(1).textContent()) ?? '').trim()
    // Wait for the PATCH to the conversation to complete before reloading.
    const patchDone = page.waitForResponse(
      (resp) => resp.url().includes(`/api/chat/conversations/${convId}`) && resp.request().method() === 'PATCH',
      { timeout: 15_000 },
    )
    await options.nth(1).click()
    await patchDone
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('chat-model-select')).toContainText(targetName.slice(0, 12), {
      timeout: 10_000,
    })
  })

  test('sends a message with the chosen model', async ({ page }) => {
    test.setTimeout(30_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    await page.getByTestId('chat-model-select').click()
    const options = page.getByRole('option')
    const count = await options.count()
    if (count >= 1) await options.first().click()
    const cleanup = await installChatStreamMock(page, {
      script: { userText: 'Reply with exactly the word OK.', assistantText: 'OK' },
    })
    try {
      await sendMessage(page, 'Reply with exactly the word OK.')
      await expect(page.getByTestId('chat-message-assistant').last()).toBeVisible()
    } finally {
      await cleanup()
    }
  })

  // ──────────────────────────────────────────────────────────────
  // New conversation from sidebar
  // ──────────────────────────────────────────────────────────────

  test('new conversation button creates and navigates to a fresh chat', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('textbox', { name: /message/i })).toBeVisible()
  })

  test('conversation appears in the sidebar after first message', async ({ page }) => {
    test.setTimeout(90_000)
    await createOrFindConversation(page, E2E_CHAT_SEND_SHARED)
    const cleanup = await installChatStreamMock(page, {
      script: { userText: 'Hello world!', assistantText: 'OK' },
    })
    try {
      await sendMessage(page, 'Hello world!')
      await page.goto('/chat/conversations', { waitUntil: 'domcontentloaded' })
      await expect(page.locator('aside a[href*="/chat/conversations/"]').first()).toBeVisible({
        timeout: 15_000,
      })
    } finally {
      await cleanup()
    }
  })
})
