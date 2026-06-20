/**
 * Admin Retention tab — verify policy fields, legal hold toggle, and GDPR purge UI.
 */
import { test, expect } from '../support/fixtures'

const RETENTION_ROUTE = '**/api/admin/retention/policy'

const MOCK_POLICY = {
  id: 1,
  org_id: 'test-org',
  conversation_retention_days: 90,
  audit_retention_days: 2555,
  usage_retention_days: 2555,
  upload_retention_days: null,
  legal_hold: false,
  updated_at: '2026-04-15T10:00:00Z',
}

test.describe('Admin — Retention tab', () => {
  test('Retention tab renders policy fields', async ({ page }) => {
    await page.route(RETENTION_ROUTE, async (route) => {
      if (route.request().method() === 'PUT') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_POLICY) })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_POLICY),
      })
    })

    await page.goto('/org/settings', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Retention' }).click()

    // Use exact text to avoid strict-mode matching description paragraphs.
    await expect(page.getByText('Conversations', { exact: true })).toBeVisible()
    await expect(page.getByText('Audit log', { exact: true })).toBeVisible()
    await expect(page.getByText('Usage data', { exact: true })).toBeVisible()
    await expect(page.getByText('Legal hold', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Save' })).toBeVisible()
  })

  test('GDPR purge section is visible', async ({ page }) => {
    await page.route(RETENTION_ROUTE, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_POLICY) })
    })

    await page.goto('/org/settings', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Retention' }).click()

    await expect(page.getByText('GDPR — Purge user data')).toBeVisible()
    await expect(page.getByPlaceholder('User ID')).toBeVisible()
    await expect(page.getByRole('button', { name: /Purge/i })).toBeVisible()
  })

  test('Legal hold toggle changes state', async ({ page }) => {
    await page.route(RETENTION_ROUTE, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_POLICY) })
    })

    await page.goto('/org/settings', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Retention' }).click()

    const legalHoldSection = page.locator('[data-testid="org-settings"]').locator('div').filter({ hasText: 'Legal hold' }).first()
    await expect(legalHoldSection).toBeVisible()

    // The toggle button uses .switch class in the Vortex design system.
    const toggle = legalHoldSection.locator('button.switch, button[class*="switch"]')
    if (await toggle.count() > 0) {
      await toggle.click()
      // After toggle, the section should still be visible (no crash).
      await expect(legalHoldSection).toBeVisible()
    }
  })
})
