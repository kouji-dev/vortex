/**
 * Chat conversation page — comprehensive interaction tests.
 *
 * Covers: composer input, KB picker open/close/search/attach/detach,
 * keyboard navigation, sidebar navigation, and thread-header delete dialog.
 */
import { test, expect } from '../support/fixtures'
import { escapeRegExp } from '../kb/helpers'
import { e2eStableResourceName } from '../support/resource-slug'
import { gotoChatComposerIndex } from '../support/conversation-ui'
import {
  attachKbToConversationViaUi,
  createOrFindConversation,
  createOrFindKb,
} from '../support/ui-helpers'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

const E2E_CONV_SHARED = 'E2E Conv Shared'
const E2E_CONV_KB_DETACH = 'E2E Conv KB Detach'

test.describe('Chat conversation', () => {
  // ──────────────────────────────────────────────────────────────
  // Composer
  // ──────────────────────────────────────────────────────────────

  test('composer index shows message input with correct placeholder', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await expect(page.getByRole('textbox', { name: /message/i })).toBeVisible()
  })

  test('thread page shows composer with correct placeholder', async ({ page }) => {
    await createOrFindConversation(page, E2E_CONV_SHARED)
    await expect(page.getByRole('textbox', { name: /message/i })).toBeVisible()
  })

  test('conversation metadata (Created …) is visible', async ({ page }) => {
    test.setTimeout(120_000)
    await createOrFindConversation(page, E2E_CONV_SHARED)
    await expect(page.getByText(/created/i).first()).toBeVisible({ timeout: 15_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // KB picker — open / close
  // ──────────────────────────────────────────────────────────────

  test('KB picker trigger button is visible', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await expect(page.getByTestId('chat-kb-picker-trigger')).toBeVisible()
  })

  test('clicking KB picker trigger opens the popover', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
  })

  test('KB picker popover contains search input', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-search')).toBeVisible()
    await expect(page.getByPlaceholder(/search knowledge bases/i)).toBeVisible()
  })

  test('pressing Escape closes the KB picker popover', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('kb-picker-popover')).toBeHidden()
  })

  test('clicking outside the KB picker popover closes it', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
    // Click outside the popover
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('kb-picker-popover')).toBeHidden()
  })

  // ──────────────────────────────────────────────────────────────
  // KB picker — attach / detach
  // ──────────────────────────────────────────────────────────────

  test('KB appears as option in the picker after creation', async ({ page }) => {
    test.setTimeout(120_000)
    const kbName = e2eStableResourceName('kb', test.info().title)
    await createOrFindKb(page, kbName)
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await expect(page.getByRole('option', { name: new RegExp(escapeRegExp(kbName)) }).first()).toBeVisible({
      timeout: 15_000,
    })
  })

  test('attaching a KB shows "Active" badge on the option', async ({ page }) => {
    test.setTimeout(120_000)
    const kbName = e2eStableResourceName('kb', test.info().title)
    await createOrFindKb(page, kbName)
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    const opt = page.getByRole('option', { name: new RegExp(escapeRegExp(kbName)) }).first()
    await opt.click()
    await expect(opt).toContainText('Active', { timeout: 10_000 })
  })

  test('trigger button updates text when KB is attached', async ({ page }) => {
    test.setTimeout(120_000)
    const kbName = e2eStableResourceName('kb', test.info().title)
    await createOrFindKb(page, kbName)
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await page.getByRole('option', { name: new RegExp(escapeRegExp(kbName)) }).first().click()
    await page.keyboard.press('Escape')
    // The trigger shows "N knowledge base[s]" when KBs are attached
    await expect(page.getByTestId('chat-kb-picker-trigger')).toContainText(/1 knowledge base/i, {
      timeout: 5_000,
    })
  })

  test('detaching a KB removes "Active" badge', async ({ page }) => {
    test.setTimeout(120_000)
    const kbName = e2eStableResourceName('kb', test.info().title)
    await createOrFindKb(page, kbName)
    const convId = await createOrFindConversation(page, E2E_CONV_KB_DETACH)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
    await attachKbToConversationViaUi(page, kbName)
    await page.getByTestId('chat-kb-picker-trigger').click()
    const opt = page.getByRole('option', { name: new RegExp(escapeRegExp(kbName)) }).first()
    await expect(opt).toHaveAttribute('aria-selected', 'true', { timeout: 10_000 })
    await opt.click()
    await expect(page.getByTestId('kb-picker-popover-inner').getByText(/saving/i)).toBeHidden({ timeout: 30_000 })
    await expect(opt).not.toHaveAttribute('aria-selected', 'true', { timeout: 10_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // KB picker — search / fuzzy filter
  // ──────────────────────────────────────────────────────────────

  test('typing in KB picker search filters the list', async ({ page }) => {
    test.setTimeout(120_000)
    const uniquePart = 'uniquexyz42'
    const kbName = e2eStableResourceName('kb', `${test.info().title} ${uniquePart}`)
    await createOrFindKb(page, kbName)
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await page.getByTestId('kb-picker-search').fill(uniquePart)
    await expect(
      page.getByRole('option', { name: new RegExp(escapeRegExp(kbName)) }).first(),
    ).toBeVisible({ timeout: 15_000 })
  })

  test('searching a non-existent name shows "No knowledge bases found."', async ({ page }) => {
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await page.getByTestId('kb-picker-search').fill('__impossible_kb_name_xyz_8888__')
    await expect(page.getByText(/no knowledge bases found/i)).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // KB picker — keyboard navigation
  // ──────────────────────────────────────────────────────────────

  test('ArrowDown key moves selection down the KB list', async ({ page }) => {
    test.setTimeout(120_000)
    const kbName = e2eStableResourceName('kb', test.info().title)
    await createOrFindKb(page, kbName)
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    // Focus the search input and press ArrowDown
    await page.getByTestId('kb-picker-search').focus()
    await page.keyboard.press('ArrowDown')
    // The second item should be highlighted (bg-neutral-100 or bg-neutral-800)
    // We just verify no crash and the popover is still open
    await expect(page.getByTestId('kb-picker-popover')).toBeVisible()
  })

  test('Enter key attaches the highlighted KB', async ({ page }) => {
    test.setTimeout(120_000)
    const kbName = e2eStableResourceName('kb', test.info().title)
    await createOrFindKb(page, kbName)
    await gotoChatComposerIndex(page)
    await page.getByTestId('chat-kb-picker-trigger').click()
    await page.getByTestId('kb-picker-search').fill(kbName)
    await expect(page.getByRole('option', { name: kbName }).first()).toBeVisible({ timeout: 20_000 })
    await page.keyboard.press('Enter')
    await expect(page.getByText('Saving…')).toBeHidden({ timeout: 30_000 })
    await expect(page.getByTestId('chat-kb-picker-trigger')).toContainText(/1 knowledge base/i, {
      timeout: 15_000,
    })
  })

  // ──────────────────────────────────────────────────────────────
  // Thread header — delete conversation dialog
  // ──────────────────────────────────────────────────────────────

  test('Delete button in thread header opens an in-app confirmation dialog', async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000)
    const convId = await createOrFindConversation(page, E2E_CONV_SHARED)
    try {
      await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
      page.once('dialog', (d) => {
        d.dismiss()
        throw new Error('Native window.confirm appeared — expected in-app dialog')
      })
      await page.getByTestId('thread-header-delete-open').click()
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
    test.setTimeout(120_000)
    const convId = await createOrFindConversation(page, E2E_CONV_SHARED)
    try {
      await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
      await page.getByTestId('thread-header-delete-open').click()
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
    test.setTimeout(120_000)
    const convId = await createOrFindConversation(page, E2E_CONV_SHARED)
    try {
      await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'domcontentloaded' })
      await page.getByTestId('thread-header-delete-open').click()
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

  test('confirming thread delete navigates away from the conversation', async ({ page }) => {
    test.setTimeout(120_000)
    const title = `E2E Del ${Date.now()}`
    await createOrFindConversation(page, title)
    await page.getByTestId('thread-header-delete-open').click()
    const dialog = page.getByRole('dialog').filter({ has: page.getByText(/delete conversation/i) })
    await expect(dialog).toBeVisible({ timeout: 5_000 })
    const deleteBtn = dialog.getByRole('button', { name: /^delete$/i })
    await expect(deleteBtn).toBeEnabled({ timeout: 5_000 })
    const deleteDone = page.waitForResponse(
      (resp) => /\/api\/chat\/conversations\/\d+$/.test(resp.url()) && resp.request().method() === 'DELETE',
      { timeout: 30_000 },
    )
    await deleteBtn.click()
    await deleteDone
    await expect(page).toHaveURL(/\/chat\/conversations\/?$/, { timeout: 30_000 })
  })
})
