/**
 * Returns the URL of the documentation site.
 *
 * Priority:
 *   1. VITE_DOCS_URL env var (set in .env or Render dashboard)
 *   2. /docs relative path as fallback
 *
 * Self-hosters: set VITE_DOCS_URL to your docs domain in your .env or CI/CD env vars.
 */
export function getDocsUrl(): string {
  const fromEnv = import.meta.env.VITE_DOCS_URL
  if (fromEnv && fromEnv.trim() !== '') return fromEnv.trim()
  return '/docs'
}
