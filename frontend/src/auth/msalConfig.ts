import type { Configuration } from '@azure/msal-browser'

export function getAuthMode(): 'dev' | 'entra' {
  const m = import.meta.env.VITE_AUTH_MODE
  return m === 'entra' ? 'entra' : 'dev'
}

export function buildMsalConfig(): Configuration {
  const clientId = import.meta.env.VITE_ENTRA_SPA_CLIENT_ID ?? ''
  const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID ?? ''
  return {
    auth: {
      clientId,
      authority: `https://login.microsoftonline.com/${tenantId}`,
      redirectUri: typeof window !== 'undefined' ? window.location.origin : '/',
    },
    cache: {
      cacheLocation: 'sessionStorage',
      storeAuthStateInCookie: false,
    },
  }
}

/** Delegated scope for the AI Portal API (e.g. api://{api-app-id}/access_as_user). */
export function apiTokenRequest() {
  const scope = import.meta.env.VITE_ENTRA_API_SCOPE ?? ''
  return { scopes: scope ? [scope] : [] }
}
