/**
 * Knowledge Bases list page — table structure, Actions column, search, stats.
 */
import { test, expect } from '../support/fixtures'
import { createKbThroughUi, escapeRegExp } from './helpers'
import { e2eStableResourceName } from '../support/resource-slug'
import { createOrFindKb } from '../support/ui-helpers'

const apiBase = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'

async function deleteKbViaApi(
  request: import('@playwright/test').APIRequestContext,
  id: number,
) {
  await request.delete(`${apiBase}/api/knowledge-bases/${id}`, {
    headers: { Authorization: 'Bearer devtoken' },
  })
}

test.describe('Knowledge Bases list page', () => {
  // ──────────────────────────────────────────────────────────────
  // Page structure
  // ──────────────────────────────────────────────────────────────

  test('page heading is visible', async ({ page }) => {
    await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: /knowledge bases/i }).first()).toBeVisible()
  })

  test('"Add knowledge base" button is visible', async ({ page }) => {
    await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('button', { name: /add knowledge base/i })).toBeVisible()
  })

  test('search input is visible with correct placeholder', async ({ page }) => {
    await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
    await expect(page.getByLabel('Search knowledge bases')).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // Table columns
  // ──────────────────────────────────────────────────────────────

  test('table has Name, Size, Chunks, Created and Actions columns', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await createOrFindKb(page, name)
    try {
      await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
      const headers = page.getByRole('columnheader')
      await expect(headers.filter({ hasText: /name/i })).toBeVisible()
      await expect(headers.filter({ hasText: /size/i })).toBeVisible()
      await expect(headers.filter({ hasText: /chunks/i })).toBeVisible()
      await expect(headers.filter({ hasText: /created/i })).toBeVisible()
      await expect(headers.filter({ hasText: /actions/i })).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Actions column — View icon button
  // ──────────────────────────────────────────────────────────────

  test('each KB row has a View icon button in the Actions column', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await createOrFindKb(page, name)
    try {
      await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
      await expect(
        page.getByRole('link', { name: new RegExp(`view ${escapeRegExp(name)}`, 'i') }),
      ).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('View icon button has title "View knowledge base"', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await createOrFindKb(page, name)
    try {
      await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
      await expect(page.getByTitle('View knowledge base').first()).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('clicking View icon navigates to the KB detail page', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await createOrFindKb(page, name)
    try {
      await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
      await page
        .getByRole('link', { name: new RegExp(`view ${escapeRegExp(name)}`, 'i') })
        .click()
      await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${id}`))
      await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  // ──────────────────────────────────────────────────────────────
  // Search / filter
  // ──────────────────────────────────────────────────────────────

  test('typing in search filters the KB list', async ({ page, request }) => {
    const unique = 'uniquekbxyz42'
    const name = e2eStableResourceName('kb', `${test.info().title} ${unique}`)
    const id = await createOrFindKb(page, name)
    try {
      await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
      await page.getByLabel('Search knowledge bases').fill(unique)
      await expect(page.getByRole('row', { name: new RegExp(escapeRegExp(unique)) })).toBeVisible()
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  test('searching a non-existent name shows "No knowledge bases match your search"', async ({
    page,
  }) => {
    await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
    await page.getByLabel('Search knowledge bases').fill('__impossible_kb_zzz_9999__')
    await expect(page.getByText(/no knowledge bases match/i)).toBeVisible()
  })

  // ──────────────────────────────────────────────────────────────
  // Create KB via dialog
  // ──────────────────────────────────────────────────────────────

  test('"Add knowledge base" button opens a dialog', async ({ page }) => {
    await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: /add knowledge base/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 10_000 })
  })

  test('can create a KB through the dialog and lands on the detail page immediately', async ({
    page,
    request,
  }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await createKbThroughUi(page, name)
    try {
      await expect(page.getByRole('heading', { name, exact: true })).toBeVisible({ timeout: 15_000 })
    } finally {
      await deleteKbViaApi(request, id)
    }
  })

  // Upload → ingest → ready is covered by e2e/kb/ingest-progress.spec.ts (avoids duplicate
  // embedding load and races with parallel E2E workers).

  // ──────────────────────────────────────────────────────────────
  // KB name cell links to detail page
  // ──────────────────────────────────────────────────────────────

  test('clicking the KB name cell navigates to the detail page', async ({ page, request }) => {
    const name = e2eStableResourceName('kb', test.info().title)
    const id = await createOrFindKb(page, name)
    try {
      await page.goto('/knowledge-bases', { waitUntil: 'domcontentloaded' })
      // The name cell contains a link — click the text
      await page.getByRole('link', { name: new RegExp(escapeRegExp(name)) }).first().click()
      await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${id}`))
    } finally {
      await deleteKbViaApi(request, id)
    }
  })
})
