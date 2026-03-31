import { InteractionRequiredAuthError } from '@azure/msal-browser'

import { apiTokenRequest, getAuthMode, getEntraApiScope } from '~/auth/msalConfig'
import { getMsalInstance } from '~/auth/msalInstance'

export async function getAuthHeaders(): Promise<HeadersInit> {
  const mode = getAuthMode()
  if (mode !== 'entra') {
    const t =
      import.meta.env.VITE_DEV_BEARER_TOKEN ??
      import.meta.env.VITE_DEV_TOKEN ??
      'devtoken'
    return { Authorization: `Bearer ${t}` }
  }

  if (!getEntraApiScope()) {
    throw new Error(
      'VITE_ENTRA_API_SCOPE is not set. The backend expects an access token for your API audience.',
    )
  }

  const msal = getMsalInstance()
  if (!msal) {
    throw new Error(
      'MSAL is not initialized yet (Entra). Avoid calling authorizedFetch during SSR or before EntraRoot finishes loading.',
    )
  }
  const account = msal.getActiveAccount() ?? msal.getAllAccounts()[0]
  if (!account) {
    throw new Error(
      'No Entra account in MSAL cache. Sign in again or wait until EntraAuthGate has completed.',
    )
  }
  try {
    const result = await msal.acquireTokenSilent({
      ...apiTokenRequest(),
      account,
    })
    return { Authorization: `Bearer ${result.accessToken}` }
  } catch (e) {
    if (e instanceof InteractionRequiredAuthError) {
      await msal.acquireTokenRedirect({
        ...apiTokenRequest(),
        account,
      })
    }
    throw e
  }
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
