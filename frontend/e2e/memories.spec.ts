import { test, expect } from '@playwright/test'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

async function createMemoryViaApi(
  request: import('@playwright/test').APIRequestContext,
  content: string,
): Promise<number> {
  const res = await request.post(`${apiBase}/api/users/me/memories`, {
    headers: {
      Authorization: `Bearer ${process.env.E2E_BEARER_TOKEN ?? 'devtoken'}`,
      'Content-Type': 'application/json',
    },
    data: { content },
  })
  const body = (await res.json()) as { id: number }
  return body.id
}

async function deleteMemoryViaApi(
  request: import('@playwright/test').APIRequestContext,
  id: number,
): Promise<void> {
  await request.delete(`${apiBase}/api/users/me/memories/${id}`, {
    headers: { Authorization: `Bearer ${process.env.E2E_BEARER_TOKEN ?? 'devtoken'}` },
  })
}

test.describe('Memories page', () => {
  // ──────────────────────────────────────────────────────────────
  // Navigation
  // ──────────────────────────────────────────────────────────────

  test('navigates to /memories from sidebar Memories link', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.getByRole('link', { name: /memories/i }).first().click()
    await expect(page).toHaveURL('/memories')
    await expect(page.getByRole('heading', { name: 'Memories', exact: true })).toBeVisible()
  })

  test('page heading and sub-heading are visible', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })
    await expect(page.getByRole('heading', { name: 'Memories', exact: true })).toBeVisible()
    await expect(page.getByText(/persistent facts/i)).toBeVisible()
    await expect(page.getByRole('heading', { name: /add a memory/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: /your memories/i })).toBeVisible()
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
    const input = page.getByPlaceholder(/e\.g\. I prefer/i)
    await input.fill('Some memory content')
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
    // Cleanup
    const res = await request.get(`${apiBase}/api/users/me/memories`, {
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
    const res = await request.get(`${apiBase}/api/users/me/memories`, {
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
    const res = await request.get(`${apiBase}/api/users/me/memories`, {
      headers: { Authorization: 'Bearer devtoken' },
    })
    const memories = (await res.json()) as Array<{ id: number; content: string }>
    const mem = memories.find((m) => m.content === content)
    if (mem) await deleteMemoryViaApi(request, mem.id)
  })

  // ──────────────────────────────────────────────────────────────
  // Memory list — source badge and metadata
  // ──────────────────────────────────────────────────────────────

  test('created memory shows "manual" source badge', async ({ page, request }) => {
    const content = `E2E manual-badge ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const row = page.locator('li', { hasText: content })
      await expect(row.getByText('manual')).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('created memory shows a creation date', async ({ page, request }) => {
    const content = `E2E date-display ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const row = page.locator('li', { hasText: content })
      // time element should exist in the row
      await expect(row.locator('time')).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Pause / Resume
  // ──────────────────────────────────────────────────────────────

  test('active memory shows "Pause" button', async ({ page, request }) => {
    const content = `E2E pause-btn ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const row = page.locator('li', { hasText: content })
      await expect(row.getByRole('button', { name: /pause/i })).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('pausing a memory dims the row (opacity-60)', async ({ page, request }) => {
    const content = `E2E pause-dim ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const row = page.locator('li', { hasText: content })
      await row.getByRole('button', { name: /pause/i }).click()
      await expect(row).toHaveClass(/opacity-60/, { timeout: 5_000 })
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('paused memory shows "Resume" button', async ({ page, request }) => {
    const content = `E2E resume-btn ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const row = page.locator('li', { hasText: content })
      await row.getByRole('button', { name: /pause/i }).click()
      await expect(row.getByRole('button', { name: /resume/i })).toBeVisible({ timeout: 5_000 })
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('resuming a paused memory removes opacity dimming', async ({ page, request }) => {
    const content = `E2E resume-opacity ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const row = page.locator('li', { hasText: content })
      await row.getByRole('button', { name: /pause/i }).click()
      await expect(row).toHaveClass(/opacity-60/, { timeout: 5_000 })
      await row.getByRole('button', { name: /resume/i }).click()
      await expect(row).not.toHaveClass(/opacity-60/, { timeout: 5_000 })
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Delete
  // ──────────────────────────────────────────────────────────────

  test('delete button with title "Delete memory" is visible per row', async ({
    page,
    request,
  }) => {
    const content = `E2E del-btn-visible ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const row = page.locator('li', { hasText: content })
      await expect(row.getByTitle('Delete memory')).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('cancelling the delete confirm leaves the memory intact', async ({ page, request }) => {
    const content = `E2E del-cancel ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      const row = page.locator('li', { hasText: content })
      // Dismiss the confirm dialog
      page.once('dialog', (d) => d.dismiss())
      await row.getByTitle('Delete memory').click()
      // Memory must still be visible
      await expect(page.getByText(content)).toBeVisible()
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })

  test('confirming the delete removes the memory from the list', async ({ page, request }) => {
    const content = `E2E del-confirm ${Date.now()}`
    await createMemoryViaApi(request, content) // id managed by delete itself
    await page.goto('/memories', { waitUntil: 'networkidle' })
    const row = page.locator('li', { hasText: content })
    page.once('dialog', (d) => d.accept())
    await row.getByTitle('Delete memory').click()
    await expect(page.getByText(content)).not.toBeVisible({ timeout: 5_000 })
  })

  // ──────────────────────────────────────────────────────────────
  // Empty state
  // ──────────────────────────────────────────────────────────────

  test('shows "No memories yet" message when list is empty via API cleanup', async ({
    page,
    request,
  }) => {
    // Fetch all memories and delete them
    const res = await request.get(`${apiBase}/api/users/me/memories`, {
      headers: { Authorization: 'Bearer devtoken' },
    })
    const memories = (await res.json()) as Array<{ id: number }>
    await Promise.all(memories.map((m) => deleteMemoryViaApi(request, m.id)))

    await page.goto('/memories', { waitUntil: 'networkidle' })
    await expect(page.getByText(/no memories yet/i)).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // API-created memory visible on page
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
})
