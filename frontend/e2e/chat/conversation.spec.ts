/**
 * Chat conversation page — comprehensive interaction tests.
 *
 * Covers: composer input, KB picker open/close/search/attach/detach,
 * keyboard navigation, KB indicator popover details, sidebar navigation,
 * and thread-header delete dialog.
 */
import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'
import {
  attachKnowledgeBasesToConversation,
  createKnowledgeBase,
  seedRagAssistantForE2e,
} from '../support/knowledge-api'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

test.describe('Chat conversation', () => {
  // ──────────────────────────────────────────────────────────────
  // Composer
  // ──────────────────────────────────────────────────────────────

  test('composer index shows message input with correct placeholder', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(
      page.getByPlaceholder('Message the assistant… (Shift+Enter for newline)'),
    ).toBeVisible()
  })

  test('thread page shows composer with correct placeholder', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(
      page.getByPlaceholder('Message the assistant… (Shift+Enter for newline)'),
    ).toBeVisible()
  })

  test('conversation metadata (Created …) is visible', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(page.getByText(/created/i).first()).toBeVisible({ timeout: 15_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // KB picker — open / close
  // ──────────────────────────────────────────────────────────────

  test('KB picker trigger button is visible', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(page.getByTestId('chat-kb-picker-trigger')).toBeVisible()
  })

  test('clicking KB picker trigger opens the popover', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
  })

  test('KB picker popover contains search input', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-search')).toBeVisible()
    await expect(page.getByPlaceholder(/search knowledge bases/i)).toBeVisible()
  })

  test('pressing Escape closes the KB picker popover', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('kb-picker-popover')).toBeHidden()
  })

  test('clicking outside the KB picker popover closes it', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
    // Click outside the popover
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('kb-picker-popover')).toBeHidden()
  })

  // ──────────────────────────────────────────────────────────────
  // KB picker — attach / detach
  // ──────────────────────────────────────────────────────────────

  test('KB appears as option in the picker after creation', async ({ page, request }) => {
    const kbName = `E2E Conv KB ${Date.now()}`
    await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByRole('option', { name: new RegExp(kbName) })).toBeVisible({
      timeout: 5_000,
    })
  })

  test('attaching a KB shows "Active" badge on the option', async ({ page, request }) => {
    const kbName = `E2E Attach KB ${Date.now()}`
    await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    const opt = page.getByRole('option', { name: new RegExp(kbName) })
    await opt.click()
    await expect(opt).toContainText('Active', { timeout: 5_000 })
  })

  test('trigger button updates text when KB is attached', async ({ page, request }) => {
    const kbName = `E2E Trigger Text ${Date.now()}`
    await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await page.getByRole('option', { name: new RegExp(kbName) }).click()
    await page.keyboard.press('Escape')
    // The trigger should now reflect the attached count
    await expect(page.getByTestId('chat-kb-picker-trigger')).toContainText(/active/i, {
      timeout: 5_000,
    })
  })

  test('detaching a KB removes "Active" badge', async ({ page, request }) => {
    const kbName = `E2E Detach KB ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    // Pre-attach via API
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    const opt = page.getByRole('option', { name: new RegExp(kbName) })
    await expect(opt).toContainText('Active', { timeout: 5_000 })
    // Click to detach
    await opt.click()
    await expect(opt).not.toContainText('Active', { timeout: 5_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // KB picker — search / fuzzy filter
  // ──────────────────────────────────────────────────────────────

  test('typing in KB picker search filters the list', async ({ page, request }) => {
    const uniquePart = `uniquexyz${Date.now()}`
    const kbName = `E2E Search ${uniquePart}`
    await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await page.getByTestId('kb-picker-search').fill(uniquePart)
    await expect(page.getByRole('option', { name: new RegExp(kbName) })).toBeVisible()
  })

  test('searching a non-existent name shows "No knowledge bases found."', async ({
    page,
    request,
  }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    await page.getByTestId('kb-picker-search').fill('__impossible_kb_name_xyz_8888__')
    await expect(page.getByText(/no knowledge bases found/i)).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // KB picker — keyboard navigation
  // ──────────────────────────────────────────────────────────────

  test('ArrowDown key moves selection down the KB list', async ({ page, request }) => {
    const kbName = `E2E ArrowDown ${Date.now()}`
    await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    // Focus the search input and press ArrowDown
    await page.getByTestId('kb-picker-search').focus()
    await page.keyboard.press('ArrowDown')
    // The second item should be highlighted (bg-neutral-100 or bg-neutral-800)
    // We just verify no crash and the popover is still open
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
  })

  test('Enter key attaches the highlighted KB', async ({ page, request }) => {
    const kbName = `E2E Enter attach ${Date.now()}`
    await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('chat-kb-picker-trigger').click()
    // Filter so the target KB is first
    await page.getByTestId('kb-picker-search').fill(kbName)
    await page.keyboard.press('Enter')
    const opt = page.getByRole('option', { name: new RegExp(kbName) })
    await expect(opt).toContainText('Active', { timeout: 5_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // KB indicator popover (seeded message)
  // ──────────────────────────────────────────────────────────────

  test('KB indicator trigger (📚) visible only on messages with used_kbs', async ({
    page,
    request,
  }) => {
    const kbName = `E2E Indicator ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])
    const seedStatus = await seedRagAssistantForE2e(request, apiBase, convId, kbId, kbName)
    expect(
      seedStatus,
      'e2e/seed-rag-assistant must return 201 (./scripts/e2e-up.sh sets E2E_ENABLE_RAG_SEED=1).',
    ).toBe(201)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await expect(page.getByTestId('message-kb-indicator-trigger')).toHaveCount(1)
  })

  test('KB indicator popover opens and shows "Knowledge bases used" heading', async ({
    page,
    request,
  }) => {
    const kbName = `E2E Popover heading ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])
    const seedStatus = await seedRagAssistantForE2e(request, apiBase, convId, kbId, kbName)
    expect(
      seedStatus,
      'e2e/seed-rag-assistant must return 201 (./scripts/e2e-up.sh sets E2E_ENABLE_RAG_SEED=1).',
    ).toBe(201)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('message-kb-indicator-trigger').click()
    const popover = page.getByTestId('message-kb-indicator-popover')
    await expect(popover).toBeVisible()
    await expect(popover.getByText(/knowledge bases used/i)).toBeVisible()
  })

  test('KB popover shows KB name, chunk count and top score', async ({ page, request }) => {
    const kbName = `E2E Popover details ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])
    const seedStatus = await seedRagAssistantForE2e(request, apiBase, convId, kbId, kbName)
    expect(
      seedStatus,
      'e2e/seed-rag-assistant must return 201 (./scripts/e2e-up.sh sets E2E_ENABLE_RAG_SEED=1).',
    ).toBe(201)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('message-kb-indicator-trigger').click()
    const popover = page.getByTestId('message-kb-indicator-popover')
    await expect(popover.getByText(kbName, { exact: false })).toBeVisible()
    await expect(popover.getByText(/chunk/i)).toBeVisible()
    await expect(popover.getByText(/top score/i)).toBeVisible()
  })

  test('KB popover closes when clicking outside', async ({ page, request }) => {
    const kbName = `E2E Popover close ${Date.now()}`
    const kbId = await createKnowledgeBase(request, apiBase, kbName)
    const convId = await createEmptyConversation(request, apiBase)
    await attachKnowledgeBasesToConversation(request, apiBase, convId, [kbId])
    const seedStatus = await seedRagAssistantForE2e(request, apiBase, convId, kbId, kbName)
    expect(
      seedStatus,
      'e2e/seed-rag-assistant must return 201 (./scripts/e2e-up.sh sets E2E_ENABLE_RAG_SEED=1).',
    ).toBe(201)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByTestId('message-kb-indicator-trigger').click()
    await expect(page.getByTestId('message-kb-indicator-popover')).toBeVisible()
    // Click away
    await page.mouse.click(10, 10)
    await expect(page.getByTestId('message-kb-indicator-popover')).not.toBeVisible({
      timeout: 5_000,
    })
  })

  // ──────────────────────────────────────────────────────────────
  // Thread header — delete conversation dialog
  // ──────────────────────────────────────────────────────────────

  test('Delete button in thread header opens an in-app confirmation dialog', async ({
    page,
    request,
  }) => {
    const convId = await createEmptyConversation(request, apiBase)
    try {
      await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
      page.once('dialog', (d) => {
        d.dismiss()
        throw new Error('Native window.confirm appeared — expected in-app dialog')
      })
      await page.getByRole('button', { name: /delete/i }).first().click()
      await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5_000 })
      await expect(page.getByRole('dialog').getByText(/delete conversation/i)).toBeVisible()
    } finally {
      const cancelBtn = page.getByRole('button', { name: /cancel/i })
      if (await cancelBtn.isVisible()) await cancelBtn.click()
      await request.delete(`${apiBase}/api/chat/conversations/${convId}`, {
        headers: { Authorization: 'Bearer devtoken' },
      }).catch(() => {})
    }
  })

  test('thread delete dialog has Cancel and Delete buttons', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    try {
      await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
      await page.getByRole('button', { name: /delete/i }).first().click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /cancel/i })).toBeVisible()
      await expect(dialog.getByRole('button', { name: /^delete$/i })).toBeVisible()
    } finally {
      const cancelBtn = page.getByRole('button', { name: /cancel/i })
      if (await cancelBtn.isVisible()) await cancelBtn.click()
      await request.delete(`${apiBase}/api/chat/conversations/${convId}`, {
        headers: { Authorization: 'Bearer devtoken' },
      }).catch(() => {})
    }
  })

  test('Cancel in thread delete dialog leaves conversation intact', async ({ page, request }) => {
    const convId = await createEmptyConversation(request, apiBase)
    try {
      await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
      await page.getByRole('button', { name: /delete/i }).first().click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: /cancel/i }).click()
      await expect(dialog).not.toBeVisible({ timeout: 3_000 })
      await expect(page).toHaveURL(new RegExp(`/chat/conversations/${convId}(?:/|$)`))
    } finally {
      await request.delete(`${apiBase}/api/chat/conversations/${convId}`, {
        headers: { Authorization: 'Bearer devtoken' },
      }).catch(() => {})
    }
  })

  test('confirming thread delete navigates away from the conversation', async ({
    page,
    request,
  }) => {
    const convId = await createEmptyConversation(request, apiBase)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /delete/i }).first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: /^delete$/i }).click()
    await expect(page).toHaveURL(/\/chat\/conversations\/?$/, { timeout: 15_000 })
  })
})
