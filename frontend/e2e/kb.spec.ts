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

test.describe('Knowledge bases', () => {
  test('create KB and upload document — row reflects ingest outcome', async ({ page }) => {
    test.setTimeout(180_000)
    const name = `E2E KB ${Date.now()}`
    await createKbThroughUi(page, name)

    const filePath = path.join(__dirname, 'fixtures', 'sample-e2e.txt')
    await page.getByTestId('kb-upload-input').setInputFiles(filePath)

    await expect(async () => {
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      await expect(row).toBeVisible()
      const statusCell = row.getByRole('cell').nth(1)
      const t = (await statusCell.textContent())?.trim() ?? ''
      expect(['ready', 'failed']).toContain(t)
    }).toPass({ timeout: 120_000 })
  })

  test('upload reaches ready when API has embeddings configured', async ({ page }) => {
    test.skip(
      process.env.E2E_REQUIRE_INGEST_READY !== '1',
      'Set E2E_REQUIRE_INGEST_READY=1 and start the API with a working OPENAI_API_KEY / LLM_API_KEY so embeddings succeed.',
    )
    test.setTimeout(180_000)
    const name = `E2E KB ready ${Date.now()}`
    await createKbThroughUi(page, name)

    const filePath = path.join(__dirname, 'fixtures', 'sample-e2e.txt')
    await page.getByTestId('kb-upload-input').setInputFiles(filePath)

    await expect(async () => {
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      await expect(row).toBeVisible()
      const statusCell = row.getByRole('cell').nth(1)
      const t = (await statusCell.textContent())?.trim() ?? ''
      expect(t).toBe('ready')
    }).toPass({ timeout: 120_000 })
  })
})
