import { test, expect } from '../support/fixtures'

test.describe('Auth gate (local mode simulation)', () => {
  // Skipped: VITE_AUTH_MODE is baked at build time so we can't override it at runtime
  // in Playwright. The auth gate is verified via manual smoke test (Task 4, Step 4).
  // To add automated coverage: build a separate Vite bundle with VITE_AUTH_MODE=local
  // and point a second webServer config at it.
  test.skip('redirects to /login when no token in localStorage', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      localStorage.removeItem('aip_access_token')
      localStorage.removeItem('aip_refresh_token')
    })
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
  })

  test('/login page renders sign-in form', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByPlaceholder('you@example.com')).toBeVisible()
    await expect(page.getByPlaceholder('••••••••')).toBeVisible()
  })

  test('/register page renders create account form', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByRole('heading', { name: 'Create account' })).toBeVisible()
  })

  test('/setup page renders setup form', async ({ page }) => {
    await page.goto('/setup')
    await expect(page.getByRole('heading', { name: 'Set up AI Portal' })).toBeVisible()
    await expect(page.getByPlaceholder('Acme Corp')).toBeVisible()
  })
})
