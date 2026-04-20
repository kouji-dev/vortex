/**
 * Mobile navigation E2E tests.
 *
 * All tests run at 390×844 (iPhone 14 viewport) to exercise the MobileAppShell,
 * BottomTabBar, MobileHeader, and ConversationDrawer.
 *
 * Requires the E2E backend: `./scripts/e2e-up.sh`
 */
import { test, expect } from '@playwright/test'

const MOBILE_VIEWPORT = { width: 390, height: 844 }
const STREAM_ROUTE = '**/api/chat/conversations/*/messages/stream'
const SHARED_CONV_NAME = 'E2E Mobile Nav'

/**
 * Locator for the "Close conversations" button inside the drawer header.
 * When the drawer is open (translateX(0)) this button is within the viewport.
 * When closed (-translateX(100%)) the drawer is off-screen, so the button's
 * bounding box x will be negative — Playwright's toBeInViewport() catches this.
 */
function drawerCloseButton(page: import('@playwright/test').Page) {
  return page.getByRole('button', { name: 'Close conversations' })
}

function drawerPanel(page: import('@playwright/test').Page) {
  return page.locator('[role="dialog"][aria-label="Conversations"]')
}

/**
 * Create or find a conversation on mobile. On mobile there is no desktop aside panel,
 * so we look in the ConversationDrawer or create via the composer with a mocked stream.
 */
async function mobileCreateOrFindConversation(
  page: import('@playwright/test').Page,
  name: string,
): Promise<void> {
  await page.goto('/chat/conversations', { waitUntil: 'networkidle' })

  // Try to find an existing conversation via the hamburger drawer
  const hamburger = page.getByRole('button', { name: 'Open conversations' })
  if (await hamburger.isVisible().catch(() => false)) {
    await hamburger.click()
    await expect(drawerCloseButton(page)).toBeInViewport({ timeout: 5_000 })
    const drawerLink = drawerPanel(page).getByRole('link', { name, exact: true })
    if (await drawerLink.first().isVisible().catch(() => false)) {
      await drawerLink.first().click()
      await page.waitForURL(/\/chat\/conversations\/\d+/, { timeout: 30_000 })
      return
    }
    // Conversation not in drawer — close it and create via composer
    await page.getByRole('button', { name: 'Close conversations' }).click()
    await expect(drawerCloseButton(page)).not.toBeInViewport({ timeout: 5_000 })
  }

  // Create conversation via the mobile composer with a mocked stream response
  await page.route(STREAM_ROUTE, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'data: {"event_type":"item","item":{"id":1,"thread_id":0,"turn_id":"00000000-0000-0000-0000-000000000000","kind":"assistant_text","role":"assistant","status":"done","provider":null,"model":null,"cost_usd":null,"cost_estimated":false,"latency_ms":null,"data":{"text":"OK"},"parent_item_id":null,"started_at":null,"finished_at":null,"created_at":"2026-01-01T00:00:00Z"}}\n\ndata: {"event_type":"done"}\n\n',
    })
  })
  try {
    await page.getByRole('textbox', { name: /message/i }).fill(name)
    await page.getByRole('button', { name: /send message/i }).click()
    await page.waitForURL(/\/chat\/conversations\/\d+/, { timeout: 60_000 })
    await expect(page.getByRole('button', { name: /send message/i })).toBeVisible({
      timeout: 60_000,
    })
  } finally {
    await page.unroute(STREAM_ROUTE).catch(() => undefined)
  }
}

test.describe('Mobile navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(MOBILE_VIEWPORT)
  })

  // ── Bottom tab bar ─────────────────────────────────────────────────────────

  test('bottom tab bar is visible on mobile', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
  })

  test('desktop sidebar is hidden on mobile', async ({ page }) => {
    await page.goto('/chat/conversations', { waitUntil: 'networkidle' })
    // AppSidebar wraps in a div.hidden.md:flex — the aside itself is inside that div
    const aside = page.locator('aside[aria-label="Main navigation"]')
    await expect(aside).toBeHidden()
  })

  // ── Tab navigation ─────────────────────────────────────────────────────────

  test('Chat tab navigates to /chat', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    const nav = page.getByRole('navigation', { name: 'Main navigation' })
    await nav.getByRole('link', { name: 'Chat' }).click()
    await expect(page).toHaveURL(/\/chat/, { timeout: 10_000 })
  })

  test('Knowledge Bases tab navigates to /knowledge-bases', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    const nav = page.getByRole('navigation', { name: 'Main navigation' })
    await nav.getByRole('link', { name: 'KBs' }).click()
    await expect(page).toHaveURL(/\/knowledge-bases/, { timeout: 10_000 })
  })

  // ── More tab bottom sheet ──────────────────────────────────────────────────

  test('More tab opens bottom sheet with overflow nav items', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'More navigation options' }).click()
    await expect(page.getByRole('link', { name: 'Org Settings' })).toBeVisible({ timeout: 5_000 })
  })

  test('More tab bottom sheet closes on backdrop tap', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'More navigation options' }).click()
    await expect(page.getByRole('link', { name: 'Org Settings' })).toBeVisible({ timeout: 5_000 })
    // Tap the backdrop — near the top of the screen, well above the bottom sheet
    await page.mouse.click(195, 200)
    await expect(page.getByRole('link', { name: 'Org Settings' })).toBeHidden({ timeout: 5_000 })
  })

  // ── Conversation drawer ────────────────────────────────────────────────────

  test('hamburger button opens the conversation drawer', async ({ page }) => {
    test.setTimeout(90_000)
    await mobileCreateOrFindConversation(page, SHARED_CONV_NAME)
    await page.getByRole('button', { name: 'Open conversations' }).click()
    await expect(drawerCloseButton(page)).toBeInViewport({ timeout: 5_000 })
  })

  test('conversation drawer closes on X button', async ({ page }) => {
    test.setTimeout(90_000)
    await mobileCreateOrFindConversation(page, SHARED_CONV_NAME)
    await page.getByRole('button', { name: 'Open conversations' }).click()
    await expect(drawerCloseButton(page)).toBeInViewport({ timeout: 5_000 })
    await drawerCloseButton(page).click()
    await expect(drawerCloseButton(page)).not.toBeInViewport({ timeout: 5_000 })
  })

  test('conversation drawer closes on backdrop tap', async ({ page }) => {
    test.setTimeout(90_000)
    await mobileCreateOrFindConversation(page, SHARED_CONV_NAME)
    await page.getByRole('button', { name: 'Open conversations' }).click()
    await expect(drawerCloseButton(page)).toBeInViewport({ timeout: 5_000 })
    // Tap to the right of the drawer (drawer is max-w-xs = 320px; tap beyond it)
    await page.mouse.click(370, 400)
    await expect(drawerCloseButton(page)).not.toBeInViewport({ timeout: 5_000 })
  })

  // ── Mobile composer ────────────────────────────────────────────────────────

  test('mobile composer send button is disabled when draft is empty', async ({ page }) => {
    test.setTimeout(90_000)
    await mobileCreateOrFindConversation(page, SHARED_CONV_NAME)
    const composer = page.getByRole('textbox', { name: /message/i })
    await expect(composer).toBeVisible()
    // Ensure textarea is empty
    await composer.fill('')
    await expect(page.getByRole('button', { name: /send message/i })).toBeDisabled()
  })

  test('mobile composer send button enables when text is typed', async ({ page }) => {
    test.setTimeout(90_000)
    await mobileCreateOrFindConversation(page, SHARED_CONV_NAME)
    const composer = page.getByRole('textbox', { name: /message/i })
    await expect(composer).toBeVisible()
    await composer.fill('Hello mobile')
    await expect(page.getByRole('button', { name: /send message/i })).toBeEnabled()
  })
})
