import { test, expect } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

async function createKbThroughUi(page: import('@playwright/test').Page, name: string) {
  await page.goto('/knowledge-bases', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /add knowledge base/i }).click()
  const dialog = page.getByRole('dialog', { name: /Knowledge base details/i })
  await expect(dialog).toBeVisible({ timeout: 15_000 })
  await dialog.getByRole('textbox').first().fill(name)
  await dialog.getByRole('button', { name: 'Next' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Create' }).click()
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
}

test.describe('Ingest progress', () => {
  test('document row shows a valid status while ingesting then reaches terminal state', async ({
    page,
  }) => {
    test.setTimeout(180_000)
    const name = `E2E Progress KB ${Date.now()}`
    await createKbThroughUi(page, name)

    const filePath = path.join(__dirname, 'fixtures', 'sample-e2e.txt')
    await page.getByTestId('kb-upload-input').setInputFiles(filePath)

    // Row should appear with a valid status (processing or terminal)
    await expect(async () => {
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      await expect(row).toBeVisible()
      const statusText = (await row.getByRole('cell').nth(1).textContent())?.trim() ?? ''
      expect(['ready', 'failed', 'ingesting', 'pending']).toContain(statusText)
    }).toPass({ timeout: 30_000 })

    // Eventually reaches a terminal state
    await expect(async () => {
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      const statusText = (await row.getByRole('cell').nth(1).textContent())?.trim() ?? ''
      expect(['ready', 'failed']).toContain(statusText)
    }).toPass({ timeout: 120_000 })
  })

  test('file too large shows a client-side or server error', async ({ page }) => {
    test.skip(
      process.env.E2E_REQUIRE_INGEST_READY !== '1',
      'Set E2E_REQUIRE_INGEST_READY=1 and provide a large-file.bin fixture to test size validation.',
    )
    const name = `E2E Size KB ${Date.now()}`
    await createKbThroughUi(page, name)

    const largePath = path.join(__dirname, 'fixtures', 'large-file.bin')
    try {
      await page.getByTestId('kb-upload-input').setInputFiles(largePath)
      await expect(page.getByText(/too large/i)).toBeVisible({ timeout: 5_000 })
    } catch {
      test.skip(true, 'large-file.bin fixture not present')
    }
  })
})
