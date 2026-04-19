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

  if (loading) return <p style={{ padding: 16, fontSize: 12, color: 'var(--ink-3)' }}>Loading…</p>

  return (
    <div>
      <div className="panel-head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span>Access Policies</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {saved && <span style={{ fontSize: 12, color: 'var(--green, #22c55e)' }}>Saved</span>}
          {error && <span style={{ fontSize: 12, color: 'var(--red)' }}>{error}</span>}
          <button onClick={save} disabled={saving} className="btn btn-primary btn-sm">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <div className="panel-body">
        {/* Default policy */}
        <section style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Default policy
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            {(['allow', 'deny'] as const).map((p) => (
              <label key={p} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink)', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="default_policy"
                  value={p}
                  checked={defaultPolicy === p}
                  onChange={() => setDefaultPolicy(p)}
                  style={{ accentColor: 'var(--accent)' }}
                />
                <span style={{ textTransform: 'capitalize' }}>{p} all (unless overridden)</span>
              </label>
            ))}
          </div>
          <p style={{ marginTop: 4, fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>
            &quot;Allow all&quot; is backwards-compatible. &quot;Deny all&quot; requires explicit role bindings.
          </p>
        </section>

        {/* Model allowlist */}
        <section style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Model allowlist
          </div>
          <p style={{ marginBottom: 10, fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>
            Empty = all models allowed. Check to restrict.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {models.map((m) => (
              <label key={m.slug} className="policy-row" style={{ cursor: 'pointer', gridTemplateColumns: '20px 1fr', gap: 8, padding: '6px 10px' }}>
                <input
                  type="checkbox"
                  checked={allowlist === null ? false : allowlist.includes(m.slug)}
                  onChange={() => toggleAllowlistModel(m.slug)}
                  style={{ accentColor: 'var(--accent)' }}
                />
                <span style={{ fontSize: 12, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.display_name}</span>
              </label>
            ))}
          </div>
          {allowlist === null && (
            <p style={{ marginTop: 6, fontSize: 11, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>All models allowed (no allowlist active)</p>
          )}
        </section>

        {/* Capability role bindings */}
        <section style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Capabilities — required roles
          </div>
          <p style={{ marginBottom: 10, fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>
            Empty = available to all roles.
          </p>
          <div style={{ border: '1px solid var(--line)', borderRadius: 4, overflow: 'hidden' }}>
            <div className="policy-row" style={{ gridTemplateColumns: '1fr 80px 80px 80px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)' }}>
              <span style={{ fontSize: 11, color: 'var(--ink-3)', fontWeight: 600 }}>Capability</span>
              {ROLES.map((r) => <span key={r} style={{ fontSize: 11, color: 'var(--ink-3)', fontWeight: 600, textAlign: 'center', textTransform: 'capitalize' }}>{r}</span>)}
            </div>
            {CAPABILITIES.map((cap) => (
              <div key={cap} className="policy-row" style={{ gridTemplateColumns: '1fr 80px 80px 80px' }}>
                <span className="meta" style={{ fontFamily: 'var(--font-mono)' }}>{cap}</span>
                {ROLES.map((role) => (
                  <div key={role} style={{ display: 'flex', justifyContent: 'center' }}>
                    <input
                      type="checkbox"
                      checked={(capBindings[cap] ?? []).includes(role)}
                      onChange={() => toggleRoleBinding(capBindings, setCapBindings, cap, role)}
                      style={{ accentColor: 'var(--accent)' }}
                    />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>

        {/* Tool role bindings */}
        <section>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Tools — required roles
          </div>
          <p style={{ marginBottom: 10, fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }}>
            Empty = available to all roles.
          </p>
          <div style={{ border: '1px solid var(--line)', borderRadius: 4, overflow: 'hidden' }}>
            <div className="policy-row" style={{ gridTemplateColumns: '1fr 80px 80px 80px', background: 'var(--bg-2)', borderBottom: '1px solid var(--line)' }}>
              <span style={{ fontSize: 11, color: 'var(--ink-3)', fontWeight: 600 }}>Tool</span>
              {ROLES.map((r) => <span key={r} style={{ fontSize: 11, color: 'var(--ink-3)', fontWeight: 600, textAlign: 'center', textTransform: 'capitalize' }}>{r}</span>)}
            </div>
            {TOOLS.map((tool) => (
              <div key={tool} className="policy-row" style={{ gridTemplateColumns: '1fr 80px 80px 80px' }}>
                <span className="meta" style={{ fontFamily: 'var(--font-mono)' }}>{tool}</span>
                {ROLES.map((role) => (
                  <div key={role} style={{ display: 'flex', justifyContent: 'center' }}>
                    <input
                      type="checkbox"
                      checked={(toolBindings[tool] ?? []).includes(role)}
                      onChange={() => toggleRoleBinding(toolBindings, setToolBindings, tool, role)}
                      style={{ accentColor: 'var(--accent)' }}
                    />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
