import { test, expect } from '../support/fixtures'

test.describe('Auth gate (local mode simulation)', () => {
  test('redirects to /login when no token in localStorage', async ({ page }) => {
    // Navigate to root, clear tokens, re-navigate — auth gate must redirect to /login.
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
    await expect(page.getByPlaceholder('you@company.com')).toBeVisible()
    await expect(page.getByPlaceholder('••••••••')).toBeVisible()
  })

  test('/register page renders create account form', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByRole('heading', { name: 'Create account' })).toBeVisible()
  })
})
