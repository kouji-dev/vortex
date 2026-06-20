/**
 * Admin Usage tab — verify the tab renders and shows usage data.
 *
 * Uses a mocked API so the test doesn't require real LLM calls or specific usage rows.
 */
import { test, expect } from '../support/fixtures'

const USAGE_SUMMARY_ROUTE = '**/api/admin/usage/summary**'

test.describe('Admin — Usage tab', () => {
  test('Usage tab renders stat cards and table', async ({ page }) => {
    // Mock the usage summary response.
    await page.route(USAGE_SUMMARY_ROUTE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          start: '2026-03-20T00:00:00Z',
          end: '2026-04-19T00:00:00Z',
          group_by: 'model',
          rows: [
            {
              group_key: 'claude-sonnet-4-6',
              input_tokens: 12345,
              output_tokens: 6789,
              cached_input_tokens: 1000,
              cost_usd: '0.042000',
              message_count: 7,
            },
          ],
          total_cost_usd: '0.042000',
          total_messages: 7,
        }),
      })
    })

    await page.goto('/org/settings', { waitUntil: 'domcontentloaded' })

    // Click the Usage tab.
    await page.getByRole('button', { name: 'Usage' }).click()

    // Stat cards should be visible.
    await expect(page.getByText('Total cost')).toBeVisible()
    await expect(page.getByText('Total messages')).toBeVisible()

    // Table row with the model name.
    await expect(page.getByText('claude-sonnet-4-6')).toBeVisible()
    await expect(page.getByText('$0.042000')).toBeVisible()
  })

  test('Usage tab shows empty state when no data', async ({ page }) => {
    await page.route(USAGE_SUMMARY_ROUTE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          start: '2026-03-20T00:00:00Z',
          end: '2026-04-19T00:00:00Z',
          group_by: 'model',
          rows: [],
          total_cost_usd: '0.000000',
          total_messages: 0,
        }),
      })
    })

    await page.goto('/org/settings', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Usage' }).click()
    await expect(page.getByText('No usage data')).toBeVisible()
  })
})
