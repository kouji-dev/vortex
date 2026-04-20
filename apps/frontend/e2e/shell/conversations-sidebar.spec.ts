/**
 * Conversations sidebar — selection mode, bulk delete, in-app delete dialogs.
 */
import { test, expect } from '@playwright/test'
import { createOrFindConversation } from '../support/ui-helpers'

test.describe.configure({ mode: 'serial' })

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

const POOL_A_TITLE = 'E2E Sidebar Shared A'
const POOL_B_TITLE = 'E2E Sidebar Shared B'
const POOL_C_TITLE = 'E2E Sidebar Shared C'

/** Avoid strict-mode clashes between selection-bar Cancel and dialog Cancel. */
async function closeOpenDeleteDialogIfAny(page: import('@playwright/test').Page) {
  const dlg = page.locator('[role="dialog"]').first()
  if (await dlg.isVisible().catch(() => false)) {
    await dlg.getByRole('button', { name: /^cancel$/i }).click()
    await dlg.waitFor({ state: 'hidden', timeout: 5_000 }).catch(() => {})
  }
}

test.describe('Conversations sidebar', () => {
  let poolA = 0
  let poolB = 0
  let poolC = 0

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(360_000)
    const context = await browser.newContext()
    const page = await context.newPage()
    poolA = await createOrFindConversation(page, POOL_A_TITLE)
    poolB = await createOrFindConversation(page, POOL_B_TITLE)
    poolC = await createOrFindConversation(page, POOL_C_TITLE)
    await context.close()
  })

  // ──────────────────────────────────────────────────────────────
  // Basic sidebar elements
  // ──────────────────────────────────────────────────────────────

  test('"New conversation" button / link is visible', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(page.getByTestId('sidebar-new-conversation')).toBeVisible()
  })

  test('"Conversation actions" menu button is visible', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(page.getByRole('button', { name: /conversation actions/i })).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // Selection mode — enter / exit
  // ──────────────────────────────────────────────────────────────

  test('clicking "Select conversations" enters selection mode', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await expect(page.getByRole('checkbox', { name: /select all/i })).toBeVisible({
      timeout: 5_000,
    })
  })

  test('"Cancel" button exits selection mode', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await expect(page.getByRole('checkbox', { name: /select all/i })).toBeVisible()
    await page.getByRole('button', { name: /^cancel$/i }).click()
    await expect(page.getByRole('checkbox', { name: /select all/i })).not.toBeVisible({
      timeout: 3_000,
    })
  })

  // ──────────────────────────────────────────────────────────────
  // Selection mode — Select All checkbox (tri-state)
  // ──────────────────────────────────────────────────────────────

  test('Select All checkbox is visible in selection mode', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await expect(page.getByRole('checkbox', { name: /select all/i })).toBeVisible()
  })

  test('Select All checkbox checks all conversations and shows selected count', async ({
    page,
  }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await page.getByRole('checkbox', { name: /select all/i }).click()
    await expect(page.getByText(/\d+\s+selected/i)).toBeVisible({ timeout: 3_000 })
  })

  test('Select All then uncheck disables the bulk Delete button', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    const selectAll = page.getByRole('checkbox', { name: /select all/i })
    await selectAll.click() // check all
    await selectAll.click() // uncheck all
    await expect(page.getByTestId('sidebar-bulk-delete')).toBeDisabled({ timeout: 3_000 })
  })

  test('individual conversation checkbox is visible in selection mode', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await expect(
      page.getByRole('checkbox', { name: /select conversation/i }).first(),
    ).toBeVisible({ timeout: 5_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // Single delete from sidebar — in-app dialog (hover to reveal button)
  // ──────────────────────────────────────────────────────────────

  test('hovering a conversation row reveals the delete button', async ({ page }) => {
    await page.goto(`/chat/conversations/${poolA}`, { waitUntil: 'networkidle' })
    const convLink = page.locator(`a[href*="/chat/conversations/${poolA}"]`).first()
    await convLink.hover()
    await expect(page.getByTitle('Delete conversation').first()).toBeVisible({ timeout: 3_000 })
  })

  test('sidebar single delete opens an in-app confirmation dialog', async ({ page }) => {
    await page.goto(`/chat/conversations/${poolA}`, { waitUntil: 'networkidle' })
    page.once('dialog', (d) => {
      d.dismiss()
      throw new Error('Native window.confirm appeared — expected in-app dialog')
    })
    const convLink = page.locator(`a[href*="/chat/conversations/${poolA}"]`).first()
    await convLink.hover()
    await page.getByTitle('Delete conversation').first().click()
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByRole('dialog').getByText(/delete conversation/i)).toBeVisible()
    const cancelBtn = page.getByRole('button', { name: /cancel/i })
    if (await cancelBtn.isVisible()) await cancelBtn.click()
  })

  test('sidebar single delete dialog has Cancel and Delete buttons', async ({ page }) => {
    await page.goto(`/chat/conversations/${poolA}`, { waitUntil: 'networkidle' })
    const convLink = page.locator(`a[href*="/chat/conversations/${poolA}"]`).first()
    await convLink.hover()
    await page.getByTitle('Delete conversation').first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: /cancel/i })).toBeVisible()
    await expect(dialog.getByRole('button', { name: /^delete$/i })).toBeVisible()
    await closeOpenDeleteDialogIfAny(page)
  })

  test('Cancel in sidebar delete dialog closes it without deleting', async ({ page }) => {
    await page.goto(`/chat/conversations/${poolA}`, { waitUntil: 'networkidle' })
    const convLink = page.locator(`a[href*="/chat/conversations/${poolA}"]`).first()
    await convLink.hover()
    await page.getByTitle('Delete conversation').first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible({ timeout: 3_000 })
    await expect(page.locator(`a[href*="/chat/conversations/${poolA}"]`).first()).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // Bulk delete — in-app dialog
  // ──────────────────────────────────────────────────────────────

  test('bulk delete opens an in-app dialog (not native confirm)', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(page.locator(`a[href*="/chat/conversations/${poolA}"]`).first()).toBeVisible({
      timeout: 30_000,
    })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await page.getByRole('checkbox', { name: /select all/i }).click()
    page.once('dialog', (d) => {
      d.dismiss()
      throw new Error('Native window.confirm appeared — expected in-app dialog')
    })
    await page.getByTestId('sidebar-bulk-delete').click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible({ timeout: 5_000 })
    await closeOpenDeleteDialogIfAny(page)
  })

  test('bulk delete dialog shows "Delete selected conversations?" heading', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(page.locator(`a[href*="/chat/conversations/${poolB}"]`).first()).toBeVisible({
      timeout: 30_000,
    })
    await expect(page.locator(`a[href*="/chat/conversations/${poolC}"]`).first()).toBeVisible({
      timeout: 30_000,
    })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await page.getByRole('checkbox', { name: /select all/i }).click()
    await page.getByTestId('sidebar-bulk-delete').click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible({ timeout: 5_000 })
    await expect(dialog.getByText(/delete selected conversations/i)).toBeVisible()
    await closeOpenDeleteDialogIfAny(page)
  })

  test('bulk delete Cancel closes dialog without deleting', async ({ page, request }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(page.locator(`a[href*="/chat/conversations/${poolA}"]`).first()).toBeVisible({
      timeout: 30_000,
    })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await page.getByRole('checkbox', { name: /select all/i }).click()
    await page.getByTestId('sidebar-bulk-delete').click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).not.toBeVisible({ timeout: 3_000 })
    const res = await request.get(`${apiBase}/api/chat/conversations/${poolA}`, {
      headers: { Authorization: 'Bearer devtoken' },
    })
    expect(res.status()).toBe(200)
  })
})
