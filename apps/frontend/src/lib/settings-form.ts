/**
 * Pure helpers for the Settings page. Tab definitions + KV diff + validation.
 */

export const SETTINGS_TABS = [
  { value: 'general', label: 'General' },
  { value: 'modules', label: 'Module flags' },
  { value: 'notifications', label: 'Notifications' },
  { value: 'retention', label: 'Retention' },
  { value: 'auth', label: 'Auth policy' },
] as const

export type SettingsTab = typeof SETTINGS_TABS[number]['value']

export const KNOWN_MODULES = [
  'gateway',
  'rag',
  'memories',
  'workers',
  'webhooks',
  'audit',
  'usage',
] as const

export interface SettingsField {
  key: string
  label: string
  type: 'string' | 'boolean' | 'number'
  description?: string
}

export const GENERAL_FIELDS: SettingsField[] = [
  { key: 'org_display_name', label: 'Display name', type: 'string' },
  { key: 'support_email', label: 'Support email', type: 'string' },
  { key: 'default_locale', label: 'Default locale', type: 'string', description: 'e.g. en-GB' },
]

export const NOTIFICATIONS_FIELDS: SettingsField[] = [
  { key: 'notifications.email.enabled', label: 'Email channel enabled', type: 'boolean' },
  { key: 'notifications.slack.enabled', label: 'Slack channel enabled', type: 'boolean' },
  { key: 'notifications.in_app.enabled', label: 'In-app channel enabled', type: 'boolean' },
  { key: 'notifications.from_email', label: 'From email', type: 'string' },
]

export const RETENTION_FIELDS: SettingsField[] = [
  { key: 'retention.audit_days', label: 'Audit log retention (days)', type: 'number' },
  { key: 'retention.usage_days', label: 'Usage events retention (days)', type: 'number' },
  { key: 'retention.chat_history_days', label: 'Chat history retention (days)', type: 'number' },
]

export const AUTH_FIELDS: SettingsField[] = [
  { key: 'auth.sso_required', label: 'Require SSO (block password login)', type: 'boolean' },
  { key: 'auth.mfa_required', label: 'Require MFA for all users', type: 'boolean' },
  { key: 'auth.session_max_minutes', label: 'Session max age (minutes)', type: 'number' },
  { key: 'auth.password_min_length', label: 'Min password length', type: 'number' },
]

/** Compute the diff of two KV maps. Returns only changed keys. */
export function diffSettings(
  current: Record<string, unknown>,
  edited: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const k of Object.keys(edited)) {
    if (!shallowEqual(current[k], edited[k])) out[k] = edited[k]
  }
  return out
}

function shallowEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (a == null || b == null) return a == null && b == null
  return JSON.stringify(a) === JSON.stringify(b)
}

/** Cast a raw form value into the expected type for a field. */
export function castValue(field: SettingsField, raw: string | boolean): unknown {
  if (field.type === 'boolean') return Boolean(raw)
  if (field.type === 'number') {
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  }
  return String(raw)
}

/** Validate a number-typed field input (must be >= 0). */
export function validateNumberField(raw: string): string | null {
  if (raw === '') return null // optional → unset
  const n = Number(raw)
  if (!Number.isFinite(n)) return 'Must be a number'
  if (n < 0) return 'Must be >= 0'
  return null
}
