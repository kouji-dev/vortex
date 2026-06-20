import { test, expect } from '../support/fixtures';

test.describe('Auth split layout', () => {
  test('login shows hero + form side by side on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/login');
    await expect(page.getByTestId('auth-shell')).toBeVisible();
    await expect(page.getByTestId('auth-form-card')).toBeVisible();
    const hero = page.locator('.auth-hero');
    const form = page.locator('.auth-form-side');
    const heroBox = await hero.boundingBox();
    const formBox = await form.boundingBox();
    expect(heroBox).not.toBeNull();
    expect(formBox).not.toBeNull();
    expect(formBox!.x).toBeGreaterThan(heroBox!.x + heroBox!.width - 4);
  });

  test('login collapses hero on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/login');
    await expect(page.getByTestId('auth-form-card')).toBeVisible();
    const hero = page.locator('.auth-hero');
    const heroBox = await hero.boundingBox();
    // Hero should collapse to a header strip <= 200px tall on mobile.
    expect(heroBox!.height).toBeLessThanOrEqual(200);
  });

  test('register and setup also use the split shell', async ({ page }) => {
    await page.goto('/register');
    await expect(page.getByTestId('auth-shell')).toBeVisible();
    await page.goto('/setup');
    await expect(page.getByTestId('auth-shell')).toBeVisible();
  });
});
