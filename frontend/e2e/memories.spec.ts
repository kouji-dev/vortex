import { test, expect } from '@playwright/test'

test.describe('Memories page', () => {
  test('navigates to memories from sidebar', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.getByRole('link', { name: /memories/i }).first().click()
    await expect(page).toHaveURL('/memories')
    await expect(page.getByRole('heading', { name: 'Memories', exact: true })).toBeVisible()
  })

  test('can create a manual memory', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })

    const content = `E2E prefer Python ${Date.now()}`
    await page.getByPlaceholder(/e\.g\. I prefer/i).fill(content)
    await page.getByRole('button', { name: /^add$/i }).click()

    await expect(page.getByText(content)).toBeVisible({ timeout: 5_000 })
    // Source badge should read "manual"
    await expect(
      page.locator('li', { hasText: content }).getByText('manual'),
    ).toBeVisible()
  })

  test('can pause and resume a memory', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })

    const content = `E2E toggle test ${Date.now()}`
    await page.getByPlaceholder(/e\.g\. I prefer/i).fill(content)
    await page.getByRole('button', { name: /^add$/i }).click()
    await expect(page.getByText(content)).toBeVisible({ timeout: 5_000 })

    const row = page.locator('li', { hasText: content })

    // Pause it — active item shows "Pause" button
    await row.getByRole('button', { name: /pause/i }).click()
    // Row becomes dimmed (opacity-60)
    await expect(row).toHaveClass(/opacity-60/, { timeout: 5_000 })

    // Resume it
    await row.getByRole('button', { name: /resume/i }).click()
    await expect(row).not.toHaveClass(/opacity-60/, { timeout: 5_000 })
  })

  test('can delete a memory', async ({ page }) => {
    await page.goto('/memories', { waitUntil: 'networkidle' })

    const content = `E2E delete me ${Date.now()}`
    await page.getByPlaceholder(/e\.g\. I prefer/i).fill(content)
    await page.getByRole('button', { name: /^add$/i }).click()
    await expect(page.getByText(content)).toBeVisible({ timeout: 5_000 })

    const row = page.locator('li', { hasText: content })

    // Handle window.confirm dialog
    page.on('dialog', (d) => d.accept())
    await row.getByTitle('Delete memory').click()

    await expect(page.getByText(content)).not.toBeVisible({ timeout: 5_000 })
  })
})
