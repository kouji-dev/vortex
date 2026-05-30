/**
 * Deploy-vs-runtime provider config (frontend mirror).
 *
 * The deployment declares the *available set* + endpoints + credentials per
 * provider layer (embedders, vector stores, rerankers, search providers,
 * connectors). The UI may only:
 *   - select a KB-level default among the ENABLED declared set
 *   - (search providers) pick the default-for-web among the enabled set
 *
 * It can never add a provider, edit an endpoint, or enter a secret. These pure
 * helpers gate the dropdowns so an invalid selection can't be submitted — the
 * backend re-enforces the same rule.
 */

export type ProviderEntry = {
  id: string
  enabled: boolean
  endpoint: string | null
  has_credential: boolean
  is_default: boolean
}

export type ProviderLayer = {
  layer: string
  default_id: string | null
  items: ProviderEntry[]
}

export type ProvidersConfig = {
  embedders: ProviderLayer
  vector_stores: ProviderLayer
  rerankers: ProviderLayer
  search_providers: ProviderLayer
  connectors: ProviderLayer
  chunkers: string[]
}

/** Ids the UI may offer as a selectable default (declared AND enabled). */
export function selectableIds(layer: ProviderLayer | undefined | null): string[] {
  if (!layer) return []
  return layer.items.filter((e) => e.enabled).map((e) => e.id)
}

/** True only when the value is a declared + enabled member of the layer. */
export function isSelectable(
  layer: ProviderLayer | undefined | null,
  value: string,
): boolean {
  return selectableIds(layer).includes(value)
}

/**
 * Validate a desired KB-level default for a layer.
 * Returns an error string, or null when ok.
 */
export function validateDefaultSelection(
  layer: ProviderLayer | undefined | null,
  value: string,
): string | null {
  if (!value) return 'Selection required'
  if (!layer) return 'Provider layer not configured'
  const allowed = selectableIds(layer)
  if (!allowed.includes(value)) {
    return `${value} is not enabled in this deployment`
  }
  return null
}

/**
 * Resolve the option to preselect in a dropdown: the current value if still
 * selectable, else the layer default if selectable, else the first enabled id.
 */
export function resolveSelected(
  layer: ProviderLayer | undefined | null,
  current: string | null | undefined,
): string {
  const allowed = selectableIds(layer)
  if (current && allowed.includes(current)) return current
  if (layer?.default_id && allowed.includes(layer.default_id)) {
    return layer.default_id
  }
  return allowed[0] ?? ''
}
