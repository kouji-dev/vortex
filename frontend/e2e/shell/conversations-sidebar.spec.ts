/**
 * Conversations sidebar — selection mode, bulk delete, in-app delete dialogs.
 */
import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

async function deleteConversationViaApi(
  request: import('@playwright/test').APIRequestContext,
  id: number,
) {
  await request.delete(`${apiBase}/api/chat/conversations/${id}`, {
    headers: { Authorization: 'Bearer devtoken' },
  })
}

test.describe('Conversations sidebar', () => {
  // ──────────────────────────────────────────────────────────────
  // Basic sidebar elements
  // ──────────────────────────────────────────────────────────────

  test('"New conversation" button / link is visible', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(
      page
        .getByRole('link', { name: /new conversation/i })
        .or(page.getByRole('button', { name: /new conversation/i })),
    ).toBeVisible()
  })

  test('"Conversation actions" menu button is visible', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await expect(page.getByRole('button', { name: /conversation actions/i })).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // Selection mode — enter / exit
  // ──────────────────────────────────────────────────────────────

  test('clicking "Select conversations" enters selection mode', async ({ page, request }) => {
    await createEmptyConversation(request, apiBase)
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await expect(page.getByRole('checkbox', { name: /select all/i })).toBeVisible({
      timeout: 5_000,
    })
  })

  test('"Cancel" button exits selection mode', async ({ page, request }) => {
    await createEmptyConversation(request, apiBase)
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

  test('Select All checkbox is visible in selection mode', async ({ page, request }) => {
    await createEmptyConversation(request, apiBase)
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /conversation actions/i }).click()
    await page.getByRole('menuitem', { name: /select conversations/i }).click()
    await expect(page.getByRole('checkbox', { name: /select all/i })).toBeVisible()
  })

  test('Select All checkbox checks all conversations and shows selected count', async ({
    page,
    request,
  }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
      await page.getByRole('button', { name: /conversation actions/i }).click()
      await page.getByRole('menuitem', { name: /select conversations/i }).click()
      await page.getByRole('checkbox', { name: /select all/i }).click()
      await expect(page.getByText(/\d+\s+selected/i)).toBeVisible({ timeout: 3_000 })
    } finally {
      await deleteConversationViaApi(request, id)
    }
  })

  test('Select All then uncheck disables the bulk Delete button', async ({ page, request }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
      await page.getByRole('button', { name: /conversation actions/i }).click()
      await page.getByRole('menuitem', { name: /select conversations/i }).click()
      const selectAll = page.getByRole('checkbox', { name: /select all/i })
      await selectAll.click() // check all
      await selectAll.click() // uncheck all
      await expect(page.getByTestId('sidebar-bulk-delete')).toBeDisabled({ timeout: 3_000 })
    } finally {
      await deleteConversationViaApi(request, id)
    }
  })

  test('individual conversation checkbox is visible in selection mode', async ({
    page,
    request,
  }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
      await page.getByRole('button', { name: /conversation actions/i }).click()
      await page.getByRole('menuitem', { name: /select conversations/i }).click()
      // At least one per-item checkbox should appear (aria-label includes "Select conversation")
      await expect(
        page.getByRole('checkbox', { name: /select conversation/i }).first(),
      ).toBeVisible({ timeout: 5_000 })
    } finally {
      await deleteConversationViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Single delete from sidebar — in-app dialog (hover to reveal button)
  // ──────────────────────────────────────────────────────────────

  test('hovering a conversation row reveals the delete button', async ({ page, request }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto(`/chat/conversations/${id}`, { waitUntil: 'networkidle' })
      const convLink = page.locator(`a[href*="/chat/conversations/${id}"]`).first()
      await convLink.hover()
      await expect(page.getByTitle('Delete conversation').first()).toBeVisible({ timeout: 3_000 })
    } finally {
      await deleteConversationViaApi(request, id)
    }
  })

  test('sidebar single delete opens an in-app confirmation dialog', async ({ page, request }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto(`/chat/conversations/${id}`, { waitUntil: 'networkidle' })
      page.once('dialog', (d) => {
        d.dismiss()
        throw new Error('Native window.confirm appeared — expected in-app dialog')
      })
      const convLink = page.locator(`a[href*="/chat/conversations/${id}"]`).first()
      await convLink.hover()
      await page.getByTitle('Delete conversation').first().click()
      await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5_000 })
      await expect(page.getByRole('dialog').getByText(/delete conversation/i)).toBeVisible()
    } finally {
      const cancelBtn = page.getByRole('button', { name: /cancel/i })
      if (await cancelBtn.isVisible()) await cancelBtn.click()
      await deleteConversationViaApi(request, id)
    }
  })

  test('sidebar single delete dialog has Cancel and Delete buttons', async ({ page, request }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto(`/chat/conversations/${id}`, { waitUntil: 'networkidle' })
      const convLink = page.locator(`a[href*="/chat/conversations/${id}"]`).first()
      await convLink.hover()
      await page.getByTitle('Delete conversation').first().click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /cancel/i })).toBeVisible()
      await expect(dialog.getByRole('button', { name: /^delete$/i })).toBeVisible()
    } finally {
      const cancelBtn = page.getByRole('button', { name: /cancel/i })
      if (await cancelBtn.isVisible()) await cancelBtn.click()
      await deleteConversationViaApi(request, id)
    }
  })

  test('Cancel in sidebar delete dialog closes it without deleting', async ({ page, request }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto(`/chat/conversations/${id}`, { waitUntil: 'networkidle' })
      const convLink = page.locator(`a[href*="/chat/conversations/${id}"]`).first()
      await convLink.hover()
      await page.getByTitle('Delete conversation').first().click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: /cancel/i }).click()
      await expect(dialog).not.toBeVisible({ timeout: 3_000 })
      await expect(page.locator(`a[href*="/chat/conversations/${id}"]`).first()).toBeVisible()
    } finally {
      await deleteConversationViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Bulk delete — in-app dialog
  // ──────────────────────────────────────────────────────────────

  test('bulk delete opens an in-app dialog (not native confirm)', async ({ page, request }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
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
    } finally {
      const cancelBtn = page.getByRole('button', { name: /cancel/i })
      if (await cancelBtn.isVisible()) await cancelBtn.click()
      await deleteConversationViaApi(request, id).catch(() => {})
    }
  })

  test('bulk delete dialog shows "Delete selected conversations?" heading', async ({
    page,
    request,
  }) => {
    const id1 = await createEmptyConversation(request, apiBase)
    const id2 = await createEmptyConversation(request, apiBase)
    try {
      await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
      await page.getByRole('button', { name: /conversation actions/i }).click()
      await page.getByRole('menuitem', { name: /select conversations/i }).click()
      await page.getByRole('checkbox', { name: /select all/i }).click()
      await page.getByTestId('sidebar-bulk-delete').click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible({ timeout: 5_000 })
      await expect(dialog.getByText(/delete selected conversations/i)).toBeVisible()
    } finally {
      const cancelBtn = page.getByRole('button', { name: /cancel/i })
      if (await cancelBtn.isVisible()) await cancelBtn.click()
      await deleteConversationViaApi(request, id1).catch(() => {})
      await deleteConversationViaApi(request, id2).catch(() => {})
    }
  })

  test('bulk delete Cancel closes dialog without deleting', async ({ page, request }) => {
    const id = await createEmptyConversation(request, apiBase)
    try {
      await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
      await page.getByRole('button', { name: /conversation actions/i }).click()
      await page.getByRole('menuitem', { name: /select conversations/i }).click()
      await page.getByRole('checkbox', { name: /select all/i }).click()
      await page.getByTestId('sidebar-bulk-delete').click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: /cancel/i }).click()
      await expect(dialog).not.toBeVisible({ timeout: 3_000 })
      const res = await request.get(`${apiBase}/api/chat/conversations/${id}`, {
        headers: { Authorization: 'Bearer devtoken' },
      })
      expect(res.status()).toBe(200)
    } finally {
      await deleteConversationViaApi(request, id)
    }
  })
})
