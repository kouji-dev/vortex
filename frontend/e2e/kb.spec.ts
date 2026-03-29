import { test, expect } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

test.describe('Knowledge bases', () => {
  test('create KB and upload document', async ({ page }) => {
    const name = `E2E KB ${Date.now()}`
    await page.goto('/knowledge-bases')
    await page.getByRole('button', { name: /add knowledge base/i }).click()
    await page.getByLabel(/^name$/i).fill(name)
    await page.getByRole('button', { name: 'Next' }).click()
    await page.getByRole('button', { name: 'Create' }).click()
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()

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
})
