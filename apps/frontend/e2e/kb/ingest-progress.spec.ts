import { test, expect } from '../support/fixtures'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { E2E_FIXTURES_DIR } from '../support/fixtures-dir'
import { createKbThroughUi } from './helpers'

const UPLOAD_ROUTE = '**/api/knowledge-bases/*/documents'
const PROGRESS_ROUTE = '**/api/knowledge-bases/*/documents/*/progress'

test.describe('Ingest progress', () => {
  test('document row shows a valid status while ingesting then reaches ready', async ({ page }) => {
    test.setTimeout(60_000)
    const name = `E2E Progress KB ${Date.now()}`
    await createKbThroughUi(page, name)

    const docId = 9001
    const kbIdPlaceholder = /\/api\/knowledge-bases\/(\d+)\/documents/

    // Mock upload to return a pending document
    await page.route(UPLOAD_ROUTE, async (route) => {
      if (route.request().method() === 'POST') {
        const kbId = route.request().url().match(kbIdPlaceholder)?.[1] ?? '0'
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            results: [{
              document_id: docId,
              status: 'ingesting',
              filename: 'sample-e2e.txt',
            }],
          }),
        })
        return
      }
      // GET list: return the doc as ready
      if (route.request().method() === 'GET') {
        const kbId = route.request().url().match(kbIdPlaceholder)?.[1] ?? '0'
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{
            id: docId,
            knowledge_base_id: Number(kbId),
            filename: 'sample-e2e.txt',
            status: 'ready',
            ingest_error: null,
            created_at: new Date().toISOString(),
          }]),
        })
        return
      }
      await route.continue()
    })
    // Mock progress endpoint to return ready
    await page.route(PROGRESS_ROUTE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          document_id: docId,
          status: 'ready',
          chunks_done: 5,
          chunks_total: 5,
          ingest_error: null,
        }),
      })
    })

    const filePath = path.join(E2E_FIXTURES_DIR, 'sample-e2e.txt')
    await page.getByTestId('kb-upload-input').setInputFiles(filePath)

    const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
    await expect(row).toBeVisible({ timeout: 15_000 })
    await expect(row.getByTestId('kb-doc-status')).toHaveText('ready', { timeout: 15_000 })
  })

  test('file too large shows a client-side or server error', async ({ page }) => {
    test.setTimeout(30_000)
    const oversizedPath = path.join(os.tmpdir(), `e2e-oversized-${Date.now()}.bin`)
    fs.writeFileSync(oversizedPath, Buffer.alloc(1024 * 1024 + 1))
    try {
      const name = `E2E Size KB ${Date.now()}`
      await createKbThroughUi(page, name)
      // Mock upload to return a "too large" error (server-side error for oversized files)
      await page.route(UPLOAD_ROUTE, async (route) => {
        if (route.request().method() === 'POST') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              results: [{
                status: 'failed',
                filename: path.basename(oversizedPath),
                ingest_error: 'File too large. Maximum size is 1 MB.',
              }],
            }),
          })
          return
        }
        await route.continue()
      })
      await page.getByTestId('kb-upload-input').setInputFiles(oversizedPath)
      await expect(page.getByText(/too large/i)).toBeVisible({ timeout: 15_000 })
    } finally {
      fs.rmSync(oversizedPath, { force: true })
    }
  })
})
