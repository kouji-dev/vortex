import { useQuery } from '@tanstack/react-query'
import { PrismLogo } from '~/components/brand'

import { getApiBase } from '~/lib/api-base'
import type { CatalogModelEntry } from '~/lib/chat-types'
import { getAuthHeaders } from '~/lib/authorizedFetch'

function catalogOptionHint(m: CatalogModelEntry): string {
  const parts: string[] = []
  if (m.model_settings.reasoning.supported && m.model_settings.reasoning.efforts_available.length) {
    parts.push(`reasoning: ${m.model_settings.reasoning.efforts_available.join(', ')}`)
  }
  if (m.model_settings.features.vision) parts.push('vision')
  if (!m.model_settings.features.vision && m.accessible) parts.push('text-only')
  if (m.effort !== 'default') parts.push(m.effort)
  return parts.length ? ` · ${parts.join(' · ')}` : ''
}

export type ModelCatalogPickerProps = {
  value: string
  onChange: (modelId: string) => void
  /**
   * Persist (e.g. PATCH conversation). Not used in create-dialog flows.
   * Invoked when choosing a catalog/default option, or on custom input blur.
   */
  onCommit?: (modelId: string) => void
  disabled?: boolean
}

export function ModelCatalogPicker({
  value,
  onChange,
  onCommit,
  disabled,
}: ModelCatalogPickerProps) {
  const apiBase = getApiBase()
  const q = useQuery({
    queryKey: ['catalog-models'],
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/models`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<CatalogModelEntry[]>
    },
  })

  const models = q.data
  const inList =
    value === '' ||
    (models?.some((m) => m.api_model_id === value) ?? false)
  const selectValue = inList ? value : '__custom__'

  const handleSelectChange = (v: string) => {
    if (v === '__custom__') {
      if (inList) onChange('')
      return
    }
    onChange(v)
    onCommit?.(v)
  }

  const handleCustomBlur = () => {
    onCommit?.(value)
  }

  if (q.isError) {
    return (
      <div className="space-y-1">
        <input
          className="w-full rounded border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-600 dark:bg-neutral-900"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={handleCustomBlur}
          placeholder="Vendor model id (e.g. o3-mini, claude-opus-4-6)"
          disabled={disabled}
          aria-label="Custom model id"
        />
        <p className="text-xs text-amber-700 dark:text-amber-400">
          Model catalog could not be loaded. Enter a deployment id manually.
        </p>
      </div>
    )
  }

  const lockedWithLink = models?.filter(
    (m) => !m.accessible && m.can_request_access && m.request_access_url,
  )

  return (
    <div className="space-y-2">
      <select
        className="w-full rounded border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-600 dark:bg-neutral-900"
        value={selectValue}
        disabled={disabled || q.isPending}
        onChange={(e) => handleSelectChange(e.target.value)}
        aria-label="Model from catalog"
      >
        <option value="">Server default</option>
        {models
          ?.slice()
          .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
          .map((m) => (
            <option
              key={m.id}
              value={m.api_model_id}
              disabled={!m.accessible}
            >
              {m.display_name}
              {!m.accessible ? ' (locked)' : ''}
              {catalogOptionHint(m)}
            </option>
          ))}
        <option value="__custom__">Custom model id…</option>
      </select>

      {selectValue === '__custom__' && (
        <input
          className="w-full rounded border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-600 dark:bg-neutral-900"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={handleCustomBlur}
          placeholder="Vendor model id"
          disabled={disabled}
          aria-label="Custom model id"
        />
      )}

      {q.isPending && (
        <p className="flex items-center gap-1.5 text-xs text-neutral-500">
          <PrismLogo state="loading" size={14} />
          Loading model catalog…
        </p>
      )}

      {lockedWithLink != null && lockedWithLink.length > 0 && (
        <ul className="space-y-1 text-xs text-neutral-500">
          {lockedWithLink.map((m) => (
            <li key={m.id}>
              <a
                href={m.request_access_url!}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline decoration-dotted dark:text-blue-400"
              >
                Request access: {m.display_name}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
