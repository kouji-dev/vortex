import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { E2E_FIXTURES_DIR } from '../support/fixtures-dir'
import { createKbThroughUi } from './helpers'

test.describe('Ingest progress', () => {
  test('document row shows a valid status while ingesting then reaches ready', async ({ page }) => {
    test.setTimeout(180_000)
    const name = `E2E Progress KB ${Date.now()}`
    await createKbThroughUi(page, name)

    const filePath = path.join(E2E_FIXTURES_DIR, 'sample-e2e.txt')
    await page.getByTestId('kb-upload-input').setInputFiles(filePath)

    const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
    await expect(row).toBeVisible({ timeout: 60_000 })
    await expect(row.getByTestId('kb-doc-status')).toHaveText('ready', { timeout: 120_000 })
  })

  test('file too large shows a client-side or server error', async ({ page }) => {
    test.setTimeout(60_000)
    const oversizedPath = path.join(os.tmpdir(), `e2e-oversized-${Date.now()}.bin`)
    fs.writeFileSync(oversizedPath, Buffer.alloc(1024 * 1024 + 1))
    try {
      const name = `E2E Size KB ${Date.now()}`
      await createKbThroughUi(page, name)
      await page.getByTestId('kb-upload-input').setInputFiles(oversizedPath)
      await expect(page.getByText(/too large/i)).toBeVisible({ timeout: 15_000 })
    } finally {
      fs.rmSync(oversizedPath, { force: true })
    }
  })
})
