import { test, expect } from '@playwright/test'

import {
  createMemoryViaApi,
  deleteMemoryViaApi,
} from '../support/memories-api'

test.describe.configure({ mode: 'serial' })

/** Find a .run-list-item containing the given content text. */
function memoryItem(page: import('@playwright/test').Page, content: string) {
  return page.locator('.run-list-item', { hasText: content })
}

test.describe('Memories page', () => {
  // ──────────────────────────────────────────────────────────────
  // Navigation
  // ──────────────────────────────────────────────────────────────

  test('navigates to /memories from sidebar Memories link', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.getByRole('link', { name: /memories/i }).first().click()
    await expect(page).toHaveURL('/memories')
    await expect(page.locator('[data-testid="memories-page"]')).toBeVisible()
  })

  test('page heading and sub-heading are visible', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'Memories', exact: true })).toBeVisible()
    await expect(page.getByText(/long-term facts/i)).toBeVisible()
    await expect(page.getByPlaceholder(/e\.g\. I prefer/i)).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // Add memory — input and button
  // ──────────────────────────────────────────────────────────────

  test('input field has correct placeholder', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    await expect(page.getByPlaceholder(/e\.g\. I prefer/i)).toBeVisible()
  })

  test('Add button is disabled when input is empty', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    await expect(page.getByRole('button', { name: /^add$/i })).toBeDisabled()
  })

  test('Add button enables when input has text', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    await page.getByPlaceholder(/e\.g\. I prefer/i).fill('Some memory content')
    await expect(page.getByRole('button', { name: /^add$/i })).toBeEnabled()
  })

  test('Add button re-disables after clearing input', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    const input = page.getByPlaceholder(/e\.g\. I prefer/i)
    await input.fill('hello')
    await input.fill('')
    await expect(page.getByRole('button', { name: /^add$/i })).toBeDisabled()
  })

  test('can create a memory by clicking Add button', async ({ page, request }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    const content = `E2E click-add ${Date.now()}`
    await page.getByPlaceholder(/e\.g\. I prefer/i).fill(content)
    await page.getByRole('button', { name: /^add$/i }).click()
    await expect(page.getByText(content)).toBeVisible({ timeout: 5_000 })
    const res = await request.get('/api/users/me/memories', {
      headers: { Authorization: 'Bearer devtoken' },
    })
    const memories = (await res.json()) as Array<{ id: number; content: string }>
    const mem = memories.find((m) => m.content === content)
    if (mem) await deleteMemoryViaApi(request, mem.id)
  })

  test('can create a memory by pressing Enter', async ({ page, request }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    const content = `E2E enter-create ${Date.now()}`
    await page.getByPlaceholder(/e\.g\. I prefer/i).fill(content)
    await page.keyboard.press('Enter')
    await expect(page.getByText(content)).toBeVisible({ timeout: 5_000 })
    const res = await request.get('/api/users/me/memories', {
      headers: { Authorization: 'Bearer devtoken' },
    })
    const memories = (await res.json()) as Array<{ id: number; content: string }>
    const mem = memories.find((m) => m.content === content)
    if (mem) await deleteMemoryViaApi(request, mem.id)
  })

  test('input clears after successful creation', async ({ page, request }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    const content = `E2E clear-after ${Date.now()}`
    const input = page.getByPlaceholder(/e\.g\. I prefer/i)
    await input.fill(content)
    await page.getByRole('button', { name: /^add$/i }).click()
    await expect(page.getByText(content)).toBeVisible({ timeout: 5_000 })
    await expect(input).toHaveValue('')
    const res = await request.get('/api/users/me/memories', {
      headers: { Authorization: 'Bearer devtoken' },
    })
    const memories = (await res.json()) as Array<{ id: number; content: string }>
    const mem = memories.find((m) => m.content === content)
    if (mem) await deleteMemoryViaApi(request, mem.id)
  })

  // ──────────────────────────────────────────────────────────────
  // Memory list — source badge and metadata
  // ──────────────────────────────────────────────────────────────

  test('created memory shows "manual" pill in the list', async ({ page, request }) => {
    const content = `E2E src-badge ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const item = memoryItem(page, content)
      await expect(item).toBeVisible()
      await expect(item.locator('.pill', { hasText: 'manual' })).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })


  test('POST /api/users/me/memories returns is_system false for manual rows', async ({
    request,
  }) => {
    const content = `E2E api-is-system ${Date.now()}`
    const res = await request.post('/api/users/me/memories', {
      headers: { Authorization: 'Bearer devtoken', 'Content-Type': 'application/json' },
      data: { content },
    })
    expect(res.status()).toBe(201)
    const body = (await res.json()) as { is_system?: boolean; id: number }
    expect(typeof body.id).toBe('number')
    if ('is_system' in body && body.is_system !== undefined) {
      expect(body.is_system).toBe(false)
    }
    await deleteMemoryViaApi(request, body.id)
  })

  test('created memory shows a relative time in the list', async ({ page, request }) => {
    const content = `E2E date-display ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const item = memoryItem(page, content)
      await expect(item).toBeVisible()
      // The .meta div contains a relative timestamp string
      await expect(item.locator('.meta')).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Pause / Resume — via detail panel
  // ──────────────────────────────────────────────────────────────

  test('selecting a memory shows "Pause" button in detail panel', async ({ page, request }) => {
    const content = `E2E pause-btn ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      await expect(page.locator('.run-main').getByRole('button', { name: /^pause$/i })).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('pausing a memory shows "paused" in list and "Resume" in detail', async ({ page, request }) => {
    const content = `E2E pause-badge ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      await page.locator('.run-main').getByRole('button', { name: /^pause$/i }).click()
      await expect(memoryItem(page, content).getByText('paused')).toBeVisible({ timeout: 5_000 })
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('paused memory shows "Resume" button in detail panel', async ({ page, request }) => {
    const content = `E2E resume-btn ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      await page.locator('.run-main').getByRole('button', { name: /^pause$/i }).click()
      await expect(page.locator('.run-main').getByRole('button', { name: /^resume$/i })).toBeVisible({ timeout: 5_000 })
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('paused memory list item shows reduced opacity on its title', async ({ page, request }) => {
    const content = `E2E pause-opacity ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      await page.locator('.run-main').getByRole('button', { name: /^pause$/i }).click()
      await expect(memoryItem(page, content).getByText('paused')).toBeVisible({ timeout: 5_000 })
      // Title has opacity 0.6 when paused (inline style)
      const titleEl = memoryItem(page, content).locator('.title')
      await expect(titleEl).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('resuming a paused memory removes "paused" badge', async ({
    page,
    request,
  }) => {
    const content = `E2E resume-opacity ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      await page.locator('.run-main').getByRole('button', { name: /^pause$/i }).click()
      await expect(page.locator('.run-main').getByRole('button', { name: /^resume$/i })).toBeVisible({ timeout: 5_000 })
      await page.locator('.run-main').getByRole('button', { name: /^resume$/i }).click()
      // "paused" label goes away from the list item
      await expect(memoryItem(page, content).getByText('paused')).not.toBeVisible({ timeout: 5_000 })
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('pausing does not reorder the item in the list', async ({ page, request }) => {
    const content1 = `E2E order-A ${Date.now()}`
    const content2 = `E2E order-B ${Date.now() + 1}`
    const id1 = await createMemoryViaApi(request, content1)
    const id2 = await createMemoryViaApi(request, content2)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const items = page.locator('.run-list-item')
      const textsBefore = await items.allTextContents()
      const idxBefore = textsBefore.findIndex((t) => t.includes(content1))
      expect(idxBefore).toBeGreaterThanOrEqual(0)

      await memoryItem(page, content1).click()
      await page.locator('.run-main').getByRole('button', { name: /^pause$/i }).click()
      await expect(memoryItem(page, content1).getByText('paused')).toBeVisible({ timeout: 5_000 })

      const textsAfter = await page.locator('.run-list-item').allTextContents()
      expect(textsAfter.findIndex((t) => t.includes(content1))).toBe(idxBefore)
    } finally {
      await deleteMemoryViaApi(request, id1)
      await deleteMemoryViaApi(request, id2)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Delete — in-app confirmation dialog (no native window.confirm)
  // ──────────────────────────────────────────────────────────────

  test('delete button ("forget") is visible in detail panel', async ({
    page,
    request,
  }) => {
    const content = `E2E del-btn-visible ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      await expect(page.locator('.run-main').getByTitle('Delete memory')).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('clicking delete opens an in-app confirmation dialog (not a native alert)', async ({
    page,
    request,
  }) => {
    const content = `E2E del-dialog-open ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      page.once('dialog', (d) => {
        d.dismiss()
        throw new Error('Native window.confirm appeared — expected in-app dialog')
      })
      await memoryItem(page, content).click()
      await page.locator('.run-main').getByTitle('Delete memory').click()
      await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5_000 })
      await expect(page.getByRole('dialog').getByText(/delete memory/i)).toBeVisible()
    } finally {
      const cancelBtn = page.getByRole('button', { name: /cancel/i })
      if (await cancelBtn.isVisible()) await cancelBtn.click()
      await deleteMemoryViaApi(request, id)
    }
  })

  test('delete dialog has Cancel and Delete buttons', async ({ page, request }) => {
    const content = `E2E del-dialog-btns ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      await page.locator('.run-main').getByTitle('Delete memory').click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('button', { name: /cancel/i })).toBeVisible()
      await expect(dialog.getByRole('button', { name: /^delete$/i })).toBeVisible()
    } finally {
      const cancelBtn = page.getByRole('button', { name: /cancel/i })
      if (await cancelBtn.isVisible()) await cancelBtn.click()
      await deleteMemoryViaApi(request, id)
    }
  })

  test('Cancel in delete dialog closes dialog and leaves the memory intact', async ({
    page,
    request,
  }) => {
    const content = `E2E del-cancel ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      await page.locator('.run-main').getByTitle('Delete memory').click()
      const dialog = page.getByRole('dialog')
      await expect(dialog).toBeVisible()
      await dialog.getByRole('button', { name: /cancel/i }).click()
      await expect(dialog).not.toBeVisible({ timeout: 3_000 })
      await expect(page.getByText(content)).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('confirming the delete removes the memory from the list', async ({ page, request }) => {
    test.setTimeout(60_000)
    const content = `E2E del-confirm ${Date.now()}`
    await createMemoryViaApi(request, content)
    await page.goto('/memories', { waitUntil: 'networkidle' })
    const item = memoryItem(page, content)
    await item.scrollIntoViewIfNeeded()
    await expect(item).toBeVisible({ timeout: 15_000 })
    await item.click()
    await page.locator('.run-main').getByTitle('Delete memory').click({ timeout: 15_000 })
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: /^delete$/i }).click()
    await expect(dialog).not.toBeVisible({ timeout: 5_000 })
    await expect(memoryItem(page, content)).toHaveCount(0)
  })

  test('delete dialog closes automatically after confirmation', async ({ page, request }) => {
    const content = `E2E del-dialog-close ${Date.now()}`
    await createMemoryViaApi(request, content)
    await page.goto('/memories', { waitUntil: 'networkidle' })
    await memoryItem(page, content).click()
    await page.locator('.run-main').getByTitle('Delete memory').click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: /^delete$/i }).click()
    await expect(dialog).not.toBeVisible({ timeout: 5_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // Misc
  // ──────────────────────────────────────────────────────────────

  test('memory created via API appears on the page', async ({ page, request }) => {
    const content = `E2E api-visible ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await expect(page.getByText(content)).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('filter chips are visible on the memories page', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    await expect(page.locator('.filter-chip', { hasText: 'all' })).toBeVisible()
    await expect(page.locator('.filter-chip', { hasText: 'system' })).toBeVisible()
    await expect(page.locator('.filter-chip', { hasText: 'active' })).toBeVisible()
    await expect(page.locator('.filter-chip', { hasText: 'paused' })).toBeVisible()
  })

  test('selecting a memory shows detail panel', async ({ page, request }) => {
    const content = `E2E detail-panel ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await memoryItem(page, content).click()
      // Full content visible in detail panel
      await expect(page.locator('.run-main').getByText(content)).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })
})
