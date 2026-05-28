/**
 * Pure helpers for the SCIM admin page.
 */
import type { ScimPreset } from './admin-types'

export const SCIM_PRESETS: { value: ScimPreset; label: string; blurb: string }[] = [
  { value: 'generic', label: 'Generic SCIM 2.0', blurb: 'Standard RFC 7644' },
  { value: 'okta', label: 'Okta', blurb: 'Okta attribute mapping' },
  { value: 'entra', label: 'Entra ID', blurb: 'Microsoft Entra ID mapping' },
]

export const SCIM_ROLE_OPTIONS = ['owner', 'admin', 'member', 'viewer', 'service'] as const

export function validateEndpointName(v: string): string | null {
  const t = v.trim()
  if (!t) return 'Name required'
  if (t.length > 128) return 'Name too long (max 128)'
  return null
}

export function validateGroupDisplayName(v: string): string | null {
  const t = v.trim()
  if (!t) return 'Display name required'
  if (t.length > 255) return 'Display name too long (max 255)'
  return null
}

/**
 * Return the SCIM base URL for an endpoint, given the API base and endpoint id.
 * Provider docs require this as the "Tenant URL" in Okta / Entra.
 */
export function scimBaseUrl(apiBase: string, endpointId: string): string {
  // Endpoint id is bound to the token; the base URL is the same for all
  // endpoints. The id is informational to the admin viewing the page.
  return `${apiBase.replace(/\/$/, '')}/scim/v2`
}
