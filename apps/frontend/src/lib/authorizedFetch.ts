import { tokenStore } from '~/auth/tokenStore'

/**
 * Returns the Authorization header for the current session.
 *
 * Flow (single OIDC-consumer / token-bearer):
 *   1. If a stored access token exists → Bearer <token>
 *   2. Dev fallback: use VITE_DEV_BEARER_TOKEN / VITE_DEV_TOKEN / "devtoken"
 */
export async function getAuthHeaders(): Promise<HeadersInit> {
  const stored = tokenStore.getAccess()
  if (stored) {
    return { Authorization: `Bearer ${stored}` }
  }

  // Dev / CI fallback — no stored session yet (used when VITE_AUTH_MODE is absent or "dev").
  const dev =
    import.meta.env.VITE_DEV_BEARER_TOKEN ??
    import.meta.env.VITE_DEV_TOKEN ??
    'devtoken'
  return { Authorization: `Bearer ${dev}` }
}

export async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers)
  const auth = await getAuthHeaders()
  for (const [k, v] of Object.entries(auth)) {
    headers.set(k, v)
  }
  return fetch(input, { ...init, headers })
}
