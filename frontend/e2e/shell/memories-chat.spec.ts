import { test, expect } from '@playwright/test'

import { createMemoryViaApi, deleteMemoryViaApi } from '../support/memories-api'

test.describe('Memories in chat', () => {
  test('homepage shows Memories feature card that links to /memories', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await expect(page.getByText('Memories', { exact: false }).first()).toBeVisible()
    const memoriesLink = page.getByRole('link', { name: /memories/i }).first()
    await expect(memoriesLink).toBeVisible()
    await memoriesLink.click()
    await expect(page).toHaveURL('/memories')
  })

  test('memories API can create and delete a memory', async ({ request }) => {
    const content = `E2E API memory ${Date.now()}`
    const id = await createMemoryViaApi(request, content)
    expect(id).toBeGreaterThan(0)
    await deleteMemoryViaApi(request, id)
  })

  test('memories page shows memory created via API', async ({ page, request }) => {
    const content = `E2E visible ${Date.now()}`
    const id = await createMemoryViaApi(request, content)

    try {
      await page.goto('/memories', { waitUntil: 'networkidle' })
      await expect(page.getByText(content)).toBeVisible({ timeout: 5_000 })
    } finally {
      await deleteMemoryViaApi(request, id)
    }
  })
})
