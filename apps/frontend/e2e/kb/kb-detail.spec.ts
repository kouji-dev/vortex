/**
 * Knowledge Base detail page — comprehensive interaction tests.
 *
 * Covers: name/description editing, save button state, document upload,
 * document table display, document deletion, back navigation, and
 * the ingest progress indicator.
 */
import { test, expect } from '../support/fixtures'
import path from 'node:path'
import { e2eStableResourceName } from '../support/resource-slug'
import { createOrFindKb } from '../support/ui-helpers'
import { E2E_FIXTURES_DIR } from '../support/fixtures-dir'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

async function openKbDetailForTest(page: import('@playwright/test').Page, name: string): Promise<number> {
  return createOrFindKb(page, name)
}

async function deleteKbViaApi(
  request: import('@playwright/test').APIRequestContext,
  id: number,
): Promise<void> {
  await request.delete(`${apiBase}/api/knowledge-bases/${id}`, {
    headers: { Authorization: 'Bearer devtoken' },
  })
}

test.describe('KB detail page', () => {
  // ──────────────────────────────────────────────────────────────
  // Structure and navigation
  // ──────────────────────────────────────────────────────────────

  test('shows KB name as page heading', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('"All knowledge bases" back link navigates to /knowledge-bases', async ({
    page,
    request,
  }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await page.getByRole('link', { name: /all knowledge bases/i }).click()
      await expect(page).toHaveURL('/knowledge-bases')
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('shows "Details" section with Name and Description fields', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await expect(page.getByRole('heading', { name: 'Details', exact: true })).toBeVisible()
      await expect(page.getByRole('textbox', { name: /name/i })).toBeVisible()
      await expect(page.getByRole('textbox', { name: /description/i })).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('name input is pre-filled with the KB name', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await expect(page.getByRole('textbox', { name: /name/i })).toHaveValue(name)
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Save button state transitions
  // ──────────────────────────────────────────────────────────────

  test('"Save changes" button is disabled when form is clean', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await expect(page.getByRole('button', { name: /save changes/i })).toBeDisabled()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('"Save changes" button enables after editing name', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      const nameInput = page.getByRole('textbox', { name: /name/i })
      await nameInput.fill(`${name} edited`)
      await expect(page.getByRole('button', { name: /save changes/i })).toBeEnabled()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('"Save changes" button enables after editing description', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await page.getByRole('textbox', { name: /description/i }).fill('A new description')
      await expect(page.getByRole('button', { name: /save changes/i })).toBeEnabled()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('"Save changes" disables again when name is reverted to original', async ({
    page,
    request,
  }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      const nameInput = page.getByRole('textbox', { name: /name/i })
      await nameInput.fill(`${name} edited`)
      await expect(page.getByRole('button', { name: /save changes/i })).toBeEnabled()
      await nameInput.fill(name) // revert
      await expect(page.getByRole('button', { name: /save changes/i })).toBeDisabled()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('can save updated KB name', async ({ page, request }) => {
    test.setTimeout(180_000)
    const name = e2eStableResourceName('kb', test.info().title)
    const updated = `${name} UPDATED`
    const id = await openKbDetailForTest(page, name)
    try {
      const nameInput = page.getByRole('textbox', { name: /name/i })
      await nameInput.fill(updated)
      await page.getByRole('button', { name: /save changes/i }).click()
      // After save the button should return to disabled state (no unsaved changes)
      await expect(page.getByRole('button', { name: /save changes/i })).toBeDisabled({
        timeout: 5_000,
      })
      // Heading should reflect new name
      await expect(page.getByRole('heading', { name: updated, exact: true })).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Upload section
  // ──────────────────────────────────────────────────────────────

  test('upload section heading and description are visible', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await expect(page.getByRole('heading', { name: /upload documents/i })).toBeVisible()
      await expect(page.getByText(/\.txt.*\.md.*\.pdf/i)).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('file input has correct test-id', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await expect(page.getByTestId('kb-upload-input')).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('uploading a file shows it in the documents table', async ({ page, request }) => {
    test.setTimeout(60_000)
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      const filePath = path.join(E2E_FIXTURES_DIR, 'sample-e2e.txt')
      await page.getByTestId('kb-upload-input').setInputFiles(filePath)
      // The documents section heading appears
      await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible()
      // The filename appears in the table
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      await expect(row).toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  // Full ingest-to-ready is covered in kb/ingest-progress.spec.ts.

  // ──────────────────────────────────────────────────────────────
  // Document deletion
  // ──────────────────────────────────────────────────────────────

  test('each document row has a delete (Trash2) button', async ({ page, request }) => {
    test.setTimeout(60_000)
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await page.getByTestId('kb-upload-input').setInputFiles(
        path.join(E2E_FIXTURES_DIR, 'sample-e2e.txt'),
      )
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      await expect(row).toBeVisible({ timeout: 15_000 })
      await expect(row.getByTitle('Remove document')).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('cancelling document delete leaves the row intact', async ({ page, request }) => {
    test.setTimeout(60_000)
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await page.getByTestId('kb-upload-input').setInputFiles(
        path.join(E2E_FIXTURES_DIR, 'sample-e2e.txt'),
      )
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      await expect(row).toBeVisible({ timeout: 15_000 })
      page.once('dialog', (d) => d.dismiss())
      await row.getByTitle('Remove document').click()
      await expect(row).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('confirming document delete removes row from table', async ({ page, request }) => {
    test.setTimeout(60_000)
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await page.getByTestId('kb-upload-input').setInputFiles(
        path.join(E2E_FIXTURES_DIR, 'sample-e2e.txt'),
      )
      const row = page.getByRole('row', { name: /sample-e2e\.txt/ })
      await expect(row).toBeVisible({ timeout: 15_000 })
      page.once('dialog', (d) => d.accept())
      await row.getByTitle('Remove document').click()
      await expect(row).not.toBeVisible({ timeout: 10_000 })
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Documents empty state
  // ──────────────────────────────────────────────────────────────

  test('shows "No files yet" when no documents have been uploaded', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await openKbDetailForTest(page, name)
    try {
      await expect(page.getByText('No files yet.').first()).toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteKbViaApi(request, id)
    }
  })
})
