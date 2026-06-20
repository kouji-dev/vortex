import { test, expect } from '../support/fixtures'

test.describe('Worker spawn — model & effort', () => {
  test('spawn drawer shows catalog model + effort selects, no runtime select', async ({ page }) => {
    await page.goto('/workers/instances', { waitUntil: 'domcontentloaded' })
    await page.getByTestId('wk-instance-spawn-open').click()

    const drawer = page.getByTestId('wk-instance-spawn-drawer')
    await expect(drawer).toBeVisible()

    // Model select is catalog-driven and filtered to usable_in_worker (Claude/Codex),
    // so a Claude option exists and no Gemini option does.
    const model = page.getByTestId('wk-instance-spawn-model')
    await expect(model).toBeVisible()
    await expect(model.locator('option', { hasText: /claude/i }).first()).toBeAttached()
    await expect(model.locator('option', { hasText: /gemini/i })).toHaveCount(0)

    // Effort select replaces the old runtime select (runtime is inferred).
    await expect(page.getByTestId('wk-instance-spawn-effort')).toBeVisible()
    await expect(page.getByTestId('wk-instance-spawn-runtime')).toHaveCount(0)
  })
})
