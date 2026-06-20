import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import * as React from 'react'
import { tokenStore } from '~/auth/tokenStore'
import { safeRedirect } from '~/lib/safe-redirect'

export const Route = createFileRoute('/auth/callback')({
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : undefined,
  }),
  component: AuthCallbackPage,
})

/**
 * OAuth social-login callback page.
 *
 * The backend redirects here after a successful social exchange:
 *   /auth/callback#access_token=<jwt>&refresh_token=<jwt>
 *
 * Tokens arrive in the URL hash (fragment) so they never hit server logs.
 * We extract them, store them via tokenStore, then navigate to the original
 * destination (via ?redirect=) or the app root.
 */
function AuthCallbackPage() {
  const navigate = useNavigate()
  const search = useSearch({ from: '/auth/callback' })
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (typeof window === 'undefined') return

    // Parse tokens from URL hash fragment: #access_token=...&refresh_token=...
    const hash = window.location.hash.slice(1) // strip leading '#'
    const params = new URLSearchParams(hash)
    const accessToken = params.get('access_token')
    const refreshToken = params.get('refresh_token')

    if (!accessToken) {
      setError('No access token in callback URL. OAuth flow may have failed.')
      return
    }

    tokenStore.set(accessToken, refreshToken ?? '')

    // Clear the hash so the token is not in browser history
    window.history.replaceState(null, '', window.location.pathname + window.location.search)

    const destination = safeRedirect(search.redirect)
    void navigate({ to: destination, replace: true })
  }, [navigate, search.redirect])

  if (error) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <div className="max-w-md rounded-lg border border-err/40 bg-err/10 p-6 text-sm text-ink">
          <p className="mb-2 font-medium text-err">Authentication failed</p>
          <p>{error}</p>
          <a href="/login" className="mt-4 inline-block text-accent underline">
            Back to login
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-dvh items-center justify-center">
      <p className="text-sm text-ink-3">Completing sign-in…</p>
    </div>
  )
}
