/**
 * Admin Audit Log tab — verify events render and CSV export button is present.
 */
import { test, expect } from '@playwright/test'

const AUDIT_ROUTE = '**/api/admin/audit**'

test.describe('Admin — Audit Log tab', () => {
  test('Audit tab renders event table', async ({ page }) => {
    await page.route(AUDIT_ROUTE, async (route) => {
      if (route.request().url().includes('export')) {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total: 1,
          items: [
            {
              id: 1,
              actor_user_id: 42,
              actor_type: 'user',
              event_type: 'conversation.create',
              resource_type: 'conversation',
              resource_id: '99',
              action: 'create',
              created_at: '2026-04-15T10:00:00Z',
            },
          ],
        }),
      })
    })

    await page.goto('/org/settings', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Audit Log' }).click()

    // Wait for the table to appear.
    await expect(page.getByText('conversation.create')).toBeVisible({ timeout: 10_000 })
    // The Export CSV button is always shown in the header.
    await expect(page.getByRole('button', { name: 'Export CSV' })).toBeVisible({ timeout: 5_000 })
  })

  test('Audit tab filter input is present', async ({ page }) => {
    await page.route(AUDIT_ROUTE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ total: 0, items: [] }),
      })
    })

    await page.goto('/org/settings', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Audit Log' }).click()

    await expect(page.getByPlaceholder(/Filter by event type/i)).toBeVisible()
  })
})
