import { test, expect } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

test.describe('Knowledge bases', () => {
  test('create KB and upload document', async ({ page }) => {
    test.setTimeout(180_000)
    const name = `E2E KB ${Date.now()}`
    await page.goto('/knowledge-bases', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /add knowledge base/i }).click()
    const dialog = page.getByRole('dialog', { name: /Knowledge base details/i })
    await expect(dialog).toBeVisible({ timeout: 15_000 })
    await dialog.getByRole('textbox').first().fill(name)
    await dialog.getByRole('button', { name: 'Next' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Create' }).click()
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()

    const filePath = path.join(__dirname, 'fixtures', 'sample-e2e.txt')
    await page.getByTestId('kb-upload-input').setInputFiles(filePath)

    const kbIdStr = page.url().match(/\/knowledge-bases\/(\d+)/)?.[1]
    expect(kbIdStr).toBeTruthy()
    const kbId = Number(kbIdStr)
    const apiBase = (process.env.E2E_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

    // Ingest may succeed (ready) or fail without LLM_API_KEY: API still persists the row as
    // failed but returns HTTP 500, so the UI shows an alert instead of refreshing the table.
    await expect(async () => {
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      if (await row.isVisible()) {
        const statusCell = row.getByRole('cell').nth(1)
        const t = (await statusCell.textContent())?.trim() ?? ''
        expect(['ready', 'failed']).toContain(t)
        return
      }

      const alert = page.getByRole('alert')
      if (await alert.isVisible()) {
        await expect(alert).toContainText(/ingest failed/i)
        const res = await page.request.get(`${apiBase}/api/knowledge-bases/${kbId}/documents`, {
          headers: { Authorization: 'Bearer devtoken' },
        })
        if (!res.ok()) {
          throw new Error(`documents list: ${res.status()} ${await res.text()}`)
        }
        const docs = (await res.json()) as { filename: string; status: string }[]
        const doc = docs.find((d) => d.filename === 'sample-e2e.txt')
        expect(doc).toBeTruthy()
        expect(doc?.status).toBe('failed')
        return
      }

      throw new Error('Waiting for documents table row or ingest error alert')
    }).toPass({ timeout: 120_000 })
  })
})
