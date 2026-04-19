import * as React from 'react'
import { authorizedFetch } from '~/lib/authorizedFetch'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

const CAPABILITIES = ['reflection', 'research'] as const
const TOOLS = ['web_search', 'fetch_webpage', 'kb_search'] as const
const ROLES = ['member', 'admin', 'owner'] as const

interface RbacPolicy {
  id: number
  model_allowlist: string[] | null
  model_role_bindings: Record<string, string[]>
  capability_role_bindings: Record<string, string[]>
  tool_role_bindings: Record<string, string[]>
  default_policy: string
}

interface CatalogModel {
  slug: string
  display_name: string
}

export function RbacPolicyPanel() {
  const [policy, setPolicy] = React.useState<RbacPolicy | null>(null)
  const [models, setModels] = React.useState<CatalogModel[]>([])
  const [loading, setLoading] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [saved, setSaved] = React.useState(false)

  // Local draft state
  const [allowlist, setAllowlist] = React.useState<string[] | null>(null)
  const [capBindings, setCapBindings] = React.useState<Record<string, string[]>>({})
  const [toolBindings, setToolBindings] = React.useState<Record<string, string[]>>({})
  const [defaultPolicy, setDefaultPolicy] = React.useState<'allow' | 'deny'>('allow')

  React.useEffect(() => {
    setLoading(true)
    Promise.all([
      authorizedFetch(`${API_BASE}/api/admin/rbac/policy`).then((r) => r.json()),
      authorizedFetch(`${API_BASE}/api/models`).then((r) => r.json()),
    ])
      .then(([pol, mods]) => {
        setPolicy(pol)
        setAllowlist(pol.model_allowlist)
        setCapBindings(pol.capability_role_bindings ?? {})
        setToolBindings(pol.tool_role_bindings ?? {})
        setDefaultPolicy(pol.default_policy === 'deny' ? 'deny' : 'allow')
        setModels(Array.isArray(mods) ? mods : [])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  function toggleAllowlistModel(slug: string) {
    if (allowlist === null) {
      setAllowlist([slug])
    } else if (allowlist.includes(slug)) {
      const next = allowlist.filter((s) => s !== slug)
      setAllowlist(next.length === 0 ? null : next)
    } else {
      setAllowlist([...allowlist, slug])
    }
  }

  function toggleRoleBinding(
    bindings: Record<string, string[]>,
    setBindings: React.Dispatch<React.SetStateAction<Record<string, string[]>>>,
    key: string,
    role: string,
  ) {
    const current = bindings[key] ?? []
    const next = current.includes(role) ? current.filter((r) => r !== role) : [...current, role]
    setBindings({ ...bindings, [key]: next })
  }

  async function save() {
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const res = await authorizedFetch(`${API_BASE}/api/admin/rbac/policy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_allowlist: allowlist,
          model_role_bindings: policy?.model_role_bindings ?? {},
          capability_role_bindings: capBindings,
          tool_role_bindings: toolBindings,
          default_policy: defaultPolicy,
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail ?? 'Save failed')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-sm text-gray-500">Loading...</p>

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Access Policies</h2>
        <div className="flex items-center gap-3">
          {saved && <span className="text-sm text-green-600 dark:text-green-400">Saved</span>}
          {error && <span className="text-sm text-red-500">{error}</span>}
          <button
            onClick={save}
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {/* Default policy */}
      <section>
        <h3 className="mb-3 text-sm font-semibold text-gray-700 dark:text-gray-300">Default policy</h3>
        <div className="flex gap-4">
          {(['allow', 'deny'] as const).map((p) => (
            <label key={p} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input
                type="radio"
                name="default_policy"
                value={p}
                checked={defaultPolicy === p}
                onChange={() => setDefaultPolicy(p)}
                className="accent-indigo-600"
              />
              <span className="capitalize">{p} all (unless overridden)</span>
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-gray-400">
          &quot;Allow all&quot; is backwards-compatible — existing users keep access. &quot;Deny all&quot; requires explicit role bindings below.
        </p>
      </section>

      {/* Model allowlist */}
      <section>
        <h3 className="mb-1 text-sm font-semibold text-gray-700 dark:text-gray-300">Model allowlist</h3>
        <p className="mb-3 text-xs text-gray-400">
          When empty, all models are allowed. Check models to restrict access to only those.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {models.map((m) => (
            <label key={m.slug} className="flex items-center gap-2 rounded-lg border border-gray-100 dark:border-gray-800 px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/40">
              <input
                type="checkbox"
                checked={allowlist === null ? false : allowlist.includes(m.slug)}
                onChange={() => toggleAllowlistModel(m.slug)}
                className="accent-indigo-600"
              />
              <span className="truncate text-gray-700 dark:text-gray-300">{m.display_name}</span>
            </label>
          ))}
        </div>
        {allowlist === null && (
          <p className="mt-2 text-xs text-indigo-500">All models allowed (no allowlist active)</p>
        )}
      </section>

      {/* Capability role bindings */}
      <section>
        <h3 className="mb-1 text-sm font-semibold text-gray-700 dark:text-gray-300">Capabilities — required roles</h3>
        <p className="mb-3 text-xs text-gray-400">
          Select which roles may use each capability. Empty = capability available to all roles.
        </p>
        <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-800 text-left text-xs text-gray-500">
                <th className="px-4 py-2 font-medium">Capability</th>
                {ROLES.map((r) => <th key={r} className="px-4 py-2 font-medium capitalize text-center">{r}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-gray-800/50">
              {CAPABILITIES.map((cap) => (
                <tr key={cap} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="px-4 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">{cap}</td>
                  {ROLES.map((role) => (
                    <td key={role} className="px-4 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={(capBindings[cap] ?? []).includes(role)}
                        onChange={() => toggleRoleBinding(capBindings, setCapBindings, cap, role)}
                        className="accent-indigo-600"
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Tool role bindings */}
      <section>
        <h3 className="mb-1 text-sm font-semibold text-gray-700 dark:text-gray-300">Tools — required roles</h3>
        <p className="mb-3 text-xs text-gray-400">
          Select which roles may invoke each tool. Empty = tool available to all roles.
        </p>
        <div className="overflow-x-auto rounded-xl border border-gray-100 dark:border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-800 text-left text-xs text-gray-500">
                <th className="px-4 py-2 font-medium">Tool</th>
                {ROLES.map((r) => <th key={r} className="px-4 py-2 font-medium capitalize text-center">{r}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-gray-800/50">
              {TOOLS.map((tool) => (
                <tr key={tool} className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="px-4 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">{tool}</td>
                  {ROLES.map((role) => (
                    <td key={role} className="px-4 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={(toolBindings[tool] ?? []).includes(role)}
                        onChange={() => toggleRoleBinding(toolBindings, setToolBindings, tool, role)}
                        className="accent-indigo-600"
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
