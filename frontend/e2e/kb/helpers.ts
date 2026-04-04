import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

/**
 * Opens the create dialog, submits KB + connector, then expects an immediate redirect to
 * `/knowledge-bases/:id` (initial file upload, if any, continues in the background).
 */
export async function createKbThroughUi(page: Page, name: string): Promise<void> {
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
}

/** Same as {@link createKbThroughUi} but attaches an initial file; expect the document row on the detail page after background upload. */
export async function createKbWithInitialFileThroughUi(
  page: Page,
  name: string,
  filePath: string,
): Promise<void> {
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
}
