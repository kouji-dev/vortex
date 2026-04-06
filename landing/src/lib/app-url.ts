/**
 * Returns the URL of the main app (frontend).
 *
 * Priority:
 *   1. VITE_APP_URL env var (set in .env or Render dashboard)
 *   2. http://localhost:5173 in local dev (Vite default port)
 *
 * Self-hosters: set VITE_APP_URL to your app domain in your .env or CI/CD env vars.
 */
export function getAppUrl(): string {
  const fromEnv = import.meta.env.VITE_APP_URL
  if (fromEnv && fromEnv.trim() !== '') return fromEnv.trim()
  // Local dev default — matches the Vite dev server default port
  return 'http://localhost:5173'
}
