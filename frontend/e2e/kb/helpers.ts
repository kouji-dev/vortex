import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

export async function createKbThroughUi(page: Page, name: string): Promise<void> {
  await page.goto('/knowledge-bases', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /add knowledge base/i }).click()
  const dialog = page.getByRole('dialog', { name: /Knowledge base details/i })
  await expect(dialog).toBeVisible({ timeout: 15_000 })
  await dialog.getByRole('textbox').first().fill(name)
  await dialog.getByRole('button', { name: 'Next' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Create' }).click()
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
}
