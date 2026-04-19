import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

/** Escape string for safe use inside `new RegExp(...)`. */
export function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function parseKnowledgeBaseIdFromUrl(page: Page): number {
  const m = page.url().match(/\/knowledge-bases\/(\d+)/)
  if (!m) throw new Error(`expected /knowledge-bases/:id in URL, got ${page.url()}`)
  return Number(m[1])
}

/**
 * Navigate to the KB list, search by name, open an existing row if found; otherwise create via the
 * dialog. Ends on `/knowledge-bases/:id`. Returns the numeric id.
 */
export async function ensureKnowledgeBaseByName(page: Page, name: string): Promise<number> {
  await page.goto('/knowledge-bases', { waitUntil: 'networkidle' })
  await page.getByLabel('Search knowledge bases').fill(name)
  const row = page.getByRole('row', { name: new RegExp(escapeRegExp(name)) })
  if (await row.first().isVisible().catch(() => false)) {
    await row.getByRole('link', { name: new RegExp(escapeRegExp(name)) }).first().click()
  } else {
    return await createKbThroughUi(page, name)
  }
  await expect(page).toHaveURL(/\/knowledge-bases\/\d+/)
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible({ timeout: 15_000 })
  return parseKnowledgeBaseIdFromUrl(page)
}

/**
 * Opens the create dialog, submits KB + connector, then expects an immediate redirect to
 * `/knowledge-bases/:id` (initial file upload, if any, continues in the background).
 */
export async function createKbThroughUi(page: Page, name: string): Promise<number> {
  await page.goto('/knowledge-bases', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /add knowledge base/i }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible({ timeout: 15_000 })
  await dialog.getByRole('textbox').first().fill(name)
  await dialog.getByRole('button', { name: 'Next' }).click()
  await dialog.getByRole('button', { name: 'Create' }).click()
  await expect(dialog).toBeHidden({ timeout: 15_000 })
  await expect(page).toHaveURL(/\/knowledge-bases\/\d+/)
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible({ timeout: 15_000 })
  return parseKnowledgeBaseIdFromUrl(page)
}

/** Same as {@link createKbThroughUi} but attaches an initial file; expect the document row on the detail page after background upload. */
export async function createKbWithInitialFileThroughUi(
  page: Page,
  name: string,
  filePath: string,
): Promise<number> {
  await page.goto('/knowledge-bases', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /add knowledge base/i }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible({ timeout: 15_000 })
  await dialog.getByRole('textbox').first().fill(name)
  await dialog.getByRole('button', { name: 'Next' }).click()
  await dialog.getByTestId('kb-create-initial-file').setInputFiles(filePath)
  await dialog.getByRole('button', { name: 'Create' }).click()
  await expect(dialog).toBeHidden({ timeout: 15_000 })
  await expect(page).toHaveURL(/\/knowledge-bases\/\d+/)
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible({ timeout: 15_000 })
  return parseKnowledgeBaseIdFromUrl(page)
}
