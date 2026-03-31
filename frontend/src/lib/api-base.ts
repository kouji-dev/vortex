function normalizeApiOrigin(raw: string): string {
  let base = raw.trim().replace(/\/+$/, '')
  // Call sites use `${base}/api/...`. If env is `http://host:8000/api`, strip the suffix to avoid
  // `/api/api/...` and FastAPI’s generic `{"detail":"Not Found"}`.
  base = base.replace(/\/api\/?$/i, '')
  return base.replace(/\/+$/, '')
}

/**
 * Origin for API calls. Most code uses `` `${getApiBase()}/api/...` `` and `` `${getApiBase()}/health` ``.
 *
 * - If `VITE_API_URL` is set → that origin (trailing `/api` stripped).
 * - Dev + browser with no env → `''` so requests are same-origin and Vite proxies `/api` + `/health`.
 * - Prod/browser with no env → `window.location.origin` (same-host API).
 * - SSR with no env → `http://127.0.0.1:8000` (local Node reaching local API).
 */
export function getApiBase(): string {
  const fromEnv =
    typeof import.meta.env.VITE_API_URL === 'string' ? import.meta.env.VITE_API_URL.trim() : ''
  if (fromEnv.length > 0) {
    return normalizeApiOrigin(fromEnv)
  }
  if (import.meta.env.DEV && typeof window !== 'undefined') {
    return ''
  }
  if (typeof window !== 'undefined' && typeof window.location?.origin === 'string') {
    return normalizeApiOrigin(window.location.origin)
  }
  return 'http://127.0.0.1:8000'
}
