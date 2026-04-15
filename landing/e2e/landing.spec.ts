// landing/e2e/landing.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Landing page', () => {

  test('loads with Vortex title', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/Vortex/)
  })

  test('announce bar is visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/web search.*multi-model/i)).toBeVisible()
  })

  test('nav has sign in and get started', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /get started/i }).first()).toBeVisible()
  })

  test('hero h1 contains "Ask anything"', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Ask anything')
  })

  test('hero CTA "Start for free" is visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: /start for free/i })).toBeVisible()
  })

  test('logo band is present', async ({ page }) => {
    await page.goto('/')
    // Scroll to trigger the IntersectionObserver reveal and wait for element in DOM
    await page.evaluate(() => window.scrollTo(0, 600))
    await expect(page.getByText('Anthropic').first()).toBeAttached({ timeout: 10000 })
  })

  test('How It Works section has 4 tabs', async ({ page }) => {
    await page.goto('/')
    await page.locator('#hiw').scrollIntoViewIfNeeded()
    // 4 tab buttons are direct children inside #hiw
    const tabs = page.locator('#hiw button')
    await expect(tabs).toHaveCount(4)
    await expect(tabs.nth(0)).toContainText('Compose')
    await expect(tabs.nth(1)).toContainText('Process')
    await expect(tabs.nth(2)).toContainText('Knowledge')
    await expect(tabs.nth(3)).toContainText('Memory')
  })

  test('clicking Knowledge tab shows Knowledge panel', async ({ page }) => {
    await page.goto('/')
    await page.locator('#hiw').scrollIntoViewIfNeeded()
    await page.waitForTimeout(300)
    // Knowledge is the 3rd tab (index 2)
    await page.locator('#hiw button').nth(2).click()
    // Panel2 heading: "Grounded answers, not hallucinations."
    await expect(page.locator('#hiw h3:has-text("Grounded")')).toBeVisible({ timeout: 10000 })
  })

  test('clicking Memory tab shows Memory panel', async ({ page }) => {
    await page.goto('/')
    await page.locator('#hiw').scrollIntoViewIfNeeded()
    await page.waitForTimeout(300)
    // Memory is the 4th tab (index 3)
    await page.locator('#hiw button').nth(3).click()
    // Panel3 heading: "Never repeat yourself again."
    await expect(page.locator('#hiw h3:has-text("Never repeat")')).toBeVisible({ timeout: 10000 })
  })

  test('footer is present with product links', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await expect(page.getByText('Knowledge Bases').first()).toBeVisible()
    await expect(page.getByText(/Vortex\. All rights reserved/i)).toBeVisible()
  })

  test('hero app demo frame renders', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('vortex.app/chat/conversations/42')).toBeVisible()
    await expect(page.getByText('Q3 Risk Analysis').first()).toBeVisible()
  })

})
