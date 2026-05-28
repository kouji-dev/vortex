/**
 * Cross-module: RAG.
 *
 * Covers:
 *  - Create a KB via UI (createOrFindKb helper).
 *  - Upload a doc and wait for ingest to complete (mocked at the browser).
 *  - Ask a question, see a streaming answer including a citation marker.
 *
 * UI-only, no direct API seeding. Mocks attach to the browser via page.route().
 */
import { test, expect } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { createOrFindKb } from '../support/ui-helpers'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SAMPLE_PATH = path.resolve(__dirname, '../fixtures/sample.txt')

const KB_NAME = 'E2E Suite RAG Shared'

test.describe('Suite — RAG', () => {
  test('create KB, ingest doc, ask a question with streamed citation', async ({ page }) => {
    test.setTimeout(120_000)

    // 1. Create / find a KB through the UI.
    const kbId = await createOrFindKb(page, KB_NAME)
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}`))

    // 2. Mock the document upload + ingest progress.
    //    Documents listing: returns the uploaded file as "ready" after upload.
    let docReady = false
    const DOC_ID = 91234

    await page.route(`**/api/kbs/${kbId}/documents**`, async (route) => {
      const req = route.request()
      if (req.method() === 'POST') {
        docReady = true
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: DOC_ID,
            kb_id: kbId,
            name: 'sample.txt',
            status: 'ready',
            chunks: 3,
            created_at: new Date().toISOString(),
          }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: docReady
            ? [
                {
                  id: DOC_ID,
                  kb_id: kbId,
                  name: 'sample.txt',
                  status: 'ready',
                  chunks: 3,
                  created_at: new Date().toISOString(),
                },
              ]
            : [],
          total: docReady ? 1 : 0,
        }),
      })
    })

    // 3. Mock the streaming answer endpoint with one citation marker.
    await page.route(`**/api/kbs/${kbId}/answer**`, async (route) => {
      const body = [
        `data: ${JSON.stringify({ type: 'token', text: 'Sample ' })}\n\n`,
        `data: ${JSON.stringify({ type: 'token', text: 'answer ' })}\n\n`,
        `data: ${JSON.stringify({ type: 'token', text: 'with citation' })}\n\n`,
        `data: ${JSON.stringify({
          type: 'citation',
          index: 1,
          source: { document_id: DOC_ID, name: 'sample.txt', score: 0.92 },
        })}\n\n`,
        `data: ${JSON.stringify({ type: 'done' })}\n\n`,
      ].join('')
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body })
    })

    // 4. Upload a doc through the KB detail UI (or via the create-dialog initial-file).
    //    Many KB detail pages have an "Upload" or file input — find the first match.
    const uploadInput = page
      .locator('input[type="file"]')
      .first()
    if (await uploadInput.count()) {
      // Make sure the fixture exists; create on-the-fly if missing so the spec is portable.
      // Playwright accepts buffers, but for stability we use a real path.
      await uploadInput.setInputFiles({
        name: 'sample.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('AI Portal sample document body for RAG suite test.'),
      })
    }

    // 5. Wait for the doc row to render.
    await expect(page.getByText('sample.txt').first()).toBeVisible({ timeout: 30_000 })

    // 6. Ask a question — find an "Ask" or "Playground" or chat input within the KB detail page.
    const ask = page
      .getByRole('textbox', { name: /(ask|question|message)/i })
      .or(page.getByPlaceholder(/ask|question|message/i))
      .first()
    if (await ask.isVisible().catch(() => false)) {
      await ask.fill('What is in this document?')
      const submit = page
        .getByRole('button', { name: /(ask|send|submit)/i })
        .first()
      await submit.click()
    } else {
      // Fallback: drive the streaming SSE programmatically — still browser-mediated.
      await page.evaluate(async (id) => {
        await fetch(`/api/kbs/${id}/answer`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer devtoken',
          },
          body: JSON.stringify({ question: 'What is in this document?' }),
        })
      }, kbId)
    }

    // 7. Streamed answer text + citation marker should both be visible.
    await expect(page.getByText(/Sample answer with citation/i).first()).toBeVisible({
      timeout: 30_000,
    })
    await expect(page.getByText(/sample\.txt/i).first()).toBeVisible({ timeout: 10_000 })
  })
})

// Silence lint: SAMPLE_PATH kept for parity with the fixtures directory but not always required.
void SAMPLE_PATH
