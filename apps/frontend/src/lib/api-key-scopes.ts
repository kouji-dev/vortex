/**
 * Catalog of API-key scope strings (must mirror server-side rbac/catalog.py).
 * Grouped for the create dialog UI; values are the canonical permission keys.
 */
export interface ScopeGroup {
  module: string
  scopes: { key: string; label: string }[]
}

export const SCOPE_CATALOG: ScopeGroup[] = [
  {
    module: 'Gateway',
    scopes: [
      { key: 'gateway:complete', label: 'Call LLMs' },
      { key: 'gateway:embed', label: 'Call embedder' },
      { key: 'gateway:traces:read', label: 'Read traces' },
      { key: 'gateway:replay', label: 'Replay requests' },
    ],
  },
  {
    module: 'Knowledge bases',
    scopes: [
      { key: 'kb:read', label: 'Read KBs' },
      { key: 'kb:write', label: 'Write KBs' },
      { key: 'kb:create', label: 'Create KB' },
      { key: 'kb:delete', label: 'Delete KB' },
      { key: 'kb:answer', label: 'Answer over KB' },
    ],
  },
  {
    module: 'Memories',
    scopes: [
      { key: 'memory:read', label: 'Read memories' },
      { key: 'memory:write', label: 'Write memories' },
    ],
  },
  {
    module: 'Workers',
    scopes: [
      { key: 'workers:submit', label: 'Submit jobs' },
    ],
  },
  {
    module: 'Audit',
    scopes: [
      { key: 'audit:read', label: 'Read audit log' },
    ],
  },
  {
    module: 'Usage',
    scopes: [
      { key: 'usage:read', label: 'Read usage' },
    ],
  },
]

export const ALL_SCOPES: string[] = SCOPE_CATALOG.flatMap((g) => g.scopes.map((s) => s.key))

const SCOPE_LABELS: Record<string, string> = Object.fromEntries(
  SCOPE_CATALOG.flatMap((g) => g.scopes.map((s) => [s.key, s.label])),
)

export function labelForScope(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope
}

/**
 * Validate proposed scopes: each must exist in the catalog, set must be non-empty.
 * Returns error string or null.
 */
export function validateScopes(scopes: string[]): string | null {
  if (scopes.length === 0) return 'Select at least one scope'
  const unknown = scopes.filter((s) => !ALL_SCOPES.includes(s))
  if (unknown.length > 0) return `Unknown scope: ${unknown.join(', ')}`
  return null
}
