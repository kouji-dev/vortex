/**
 * Guard against open-redirect attacks on the `?redirect=` query param.
 * Only allows same-origin paths (starts with '/', not '//').
 */
export function safeRedirect(raw: string | undefined): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/'
  return raw
}
