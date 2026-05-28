/**
 * Pure helpers for the pool template editor.
 *
 * The editor lets admins paste JSON for ``pool.settings_json``. We need
 * to:
 *   - validate the user's text is parseable JSON-object (not array /
 *     scalar — settings_json is a record on the server)
 *   - produce a "dirty" flag vs. the server-side value, ignoring key
 *     ordering and insignificant whitespace
 *   - pretty-print for the textarea on load
 *
 * All logic here is DOM-free so it unit-tests without React.
 */

export type Settings = Record<string, unknown>

export interface ValidateOk {
  ok: true
  value: Settings
}

export interface ValidateErr {
  ok: false
  error: string
}

export type ValidateResult = ValidateOk | ValidateErr

/** Parse and validate a textarea string. Empty input is treated as `{}`. */
export function validateSettingsJson(text: string): ValidateResult {
  const trimmed = text.trim()
  if (trimmed === '') {
    return { ok: true, value: {} }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (e) {
    return { ok: false, error: (e as Error).message }
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return {
      ok: false,
      error: 'settings must be a JSON object (got ' + describe(parsed) + ')',
    }
  }
  return { ok: true, value: parsed as Settings }
}

function describe(v: unknown): string {
  if (v === null) return 'null'
  if (Array.isArray(v)) return 'array'
  return typeof v
}

/** Pretty-print for the textarea. Always 2-space indent, sorted keys. */
export function formatSettings(value: Settings | null | undefined): string {
  if (!value) return '{}'
  return JSON.stringify(sortKeys(value), null, 2)
}

/** Recursively sort object keys so diffs are stable. Arrays kept as-is. */
function sortKeys(v: unknown): unknown {
  if (v === null || typeof v !== 'object') return v
  if (Array.isArray(v)) return v.map(sortKeys)
  const out: Record<string, unknown> = {}
  for (const k of Object.keys(v as Record<string, unknown>).sort()) {
    out[k] = sortKeys((v as Record<string, unknown>)[k])
  }
  return out
}

/**
 * Compare current editor text to the server value. Returns ``true`` when
 * the user has made a meaningful change (ignoring formatting / key
 * order).
 */
export function isDirty(
  draftText: string,
  serverValue: Settings | null | undefined,
): boolean {
  const v = validateSettingsJson(draftText)
  if (!v.ok) {
    // Invalid input is always "dirty" — the user has typed something.
    return true
  }
  const a = JSON.stringify(sortKeys(v.value))
  const b = JSON.stringify(sortKeys(serverValue ?? {}))
  return a !== b
}
