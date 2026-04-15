import { test, expect } from '@playwright/test'

test.describe('Getting Started', () => {
  test('overview page loads with correct heading', async ({ page }) => {
    await page.goto('/getting-started/overview')
    await expect(page.getByRole('heading', { name: 'Overview', level: 1 })).toBeVisible()
    await expect(page.getByText('self-hostable AI portal')).toBeVisible()
  })

  test('prerequisites page documents required external services', async ({ page }) => {
    await page.goto('/getting-started/prerequisites')
    await expect(page.getByRole('heading', { name: 'Prerequisites', level: 1 })).toBeVisible()
    await expect(page.getByText('pgvector').first()).toBeVisible()
    await expect(page.getByText('ANTHROPIC_API_KEY').first()).toBeVisible()
    await expect(page.getByText('VOYAGE_API_KEY').first()).toBeVisible()
  })

  test('quickstart page shows config.yaml example', async ({ page }) => {
    await page.goto('/getting-started/quickstart')
    await expect(page.getByRole('heading', { name: 'Quickstart', level: 1 })).toBeVisible()
    await expect(page.getByText('deployment_mode').first()).toBeVisible()
    await expect(page.getByText('seed-catalog-models').first()).toBeVisible()
  })
})

test.describe('Installation', () => {
  test('docker-compose page shows compose commands', async ({ page }) => {
    await page.goto('/installation/docker-compose')
    await expect(page.getByRole('heading', { name: 'Docker Compose', level: 1 })).toBeVisible()
    await expect(page.getByText('docker compose up -d').first()).toBeVisible()
    await expect(page.getByText('--profile full').first()).toBeVisible()
  })

  test('manual page shows Python install steps', async ({ page }) => {
    await page.goto('/installation/manual')
    await expect(page.getByRole('heading', { name: /Manual/i, level: 1 })).toBeVisible()
    await expect(page.getByText('alembic upgrade head').first()).toBeVisible()
    await expect(page.getByText('seed-catalog-models').first()).toBeVisible()
  })
})

test.describe('Configuration Reference', () => {
  test('reference page documents all major sections', async ({ page }) => {
    await page.goto('/configuration/reference')
    await expect(page.getByRole('heading', { name: 'Configuration Reference', level: 1 })).toBeVisible()

    // Check all 12 sections are present (h2 headings use backtick formatting in MDX)
    for (const section of ['server', 'database', 'auth', 'smtp', 'llm', 'embedding', 'ingest', 'rag', 'conversation', 'observability', 'search', 'fetch']) {
      await expect(page.locator('h2').filter({ hasText: new RegExp(`^${section}$`, 'i') })).toBeVisible()
    }
  })

  test('reference page documents key env vars', async ({ page }) => {
    await page.goto('/configuration/reference')
    const criticalEnvVars = [
      'DEPLOYMENT_MODE', 'SECRET_KEY', 'DATABASE_URL', 'CORS_ORIGINS',
      'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY',
      'VOYAGE_API_KEY', 'SMTP_HOST',
    ]
    for (const envVar of criticalEnvVars) {
      await expect(page.getByText(envVar).first()).toBeVisible()
    }
  })

  test('auth page documents selfhosted first-boot flow', async ({ page }) => {
    await page.goto('/configuration/auth')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByText('503').first()).toBeVisible()
    await expect(page.getByText('/setup').first()).toBeVisible()
    await expect(page.getByText('selfhosted').first()).toBeVisible()
  })
})

test.describe('Operations', () => {
  test('troubleshooting page covers common errors', async ({ page }) => {
    await page.goto('/operations/troubleshooting')
    await expect(page.getByRole('heading', { name: 'Troubleshooting', level: 1 })).toBeVisible()
    // h2 heading: `503 Setup Required` on all routes
    await expect(page.locator('h2').filter({ hasText: '503 Setup Required' })).toBeVisible()
    // h2 heading: CORS errors in the browser
    await expect(page.locator('h2').filter({ hasText: 'CORS errors' })).toBeVisible()
    // h2 heading: `SECRET_KEY must be set` error
    await expect(page.locator('h2').filter({ hasText: 'SECRET_KEY must be set' })).toBeVisible()
  })

  test('upgrading page documents migration behavior', async ({ page }) => {
    await page.goto('/operations/upgrading')
    await expect(page.getByText('alembic upgrade head').first()).toBeVisible()
    await expect(page.getByText('seed-catalog-models').first()).toBeVisible()
  })
})

test.describe('Navigation', () => {
  test('root redirects to getting-started overview', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/getting-started\/overview/)
  })

  test('sidebar is visible on all pages', async ({ page }) => {
    await page.goto('/getting-started/overview')
    await expect(page.getByText('Getting Started').first()).toBeVisible()
    await expect(page.getByText('Installation').first()).toBeVisible()
    await expect(page.getByText('Configuration').first()).toBeVisible()
    await expect(page.getByText('Operations').first()).toBeVisible()
  })
})
