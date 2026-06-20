import { Select } from '~/components/ui/select'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Trash2 } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  CONNECTOR_KINDS,
  CONNECTOR_KIND_LABELS,
  type ConnectorKind,
  type ConnectorSyncJob,
  type KnowledgeBaseConnector,
  isConnectorKindImplemented,
  knowledgeBaseListFromResponse,
  parseConnectorSyncJobsListJson,
  parseKnowledgeBaseConnectorsListJson,
} from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

type KnowledgeBaseConnectorsSectionProps = {
  knowledgeBaseId: number
}

export function KnowledgeBaseConnectorsSection({
  knowledgeBaseId,
}: KnowledgeBaseConnectorsSectionProps) {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  const [kind, setKind] = React.useState<ConnectorKind>('files')
  const [label, setLabel] = React.useState('')
  const [settingsText, setSettingsText] = React.useState('{}')

  const settingsJsonInvalid = React.useMemo(() => {
    const t = settingsText.trim()
    if (!t) return false
    try {
      JSON.parse(t)
      return false
    } catch {
      return true
    }
  }, [settingsText])

  const connectorsQ = useQuery({
    queryKey: queryKeys.knowledgeBaseConnectors(knowledgeBaseId),
    queryFn: async () => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${knowledgeBaseId}/connectors`,
        { headers: await getAuthHeaders() },
      )
      const text = await res.text()
      return knowledgeBaseListFromResponse(res, text, parseKnowledgeBaseConnectorsListJson)
    },
  })

  const jobsQ = useQuery({
    queryKey: queryKeys.knowledgeBaseConnectorJobs(knowledgeBaseId),
    queryFn: async () => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${knowledgeBaseId}/connector-jobs?limit=50`,
        { headers: await getAuthHeaders() },
      )
      const text = await res.text()
      return knowledgeBaseListFromResponse(res, text, parseConnectorSyncJobsListJson)
    },
    refetchInterval: (query) => {
      const data = query.state.data as ConnectorSyncJob[] | undefined
      if (!data?.length) return false
      const active = data.some((j) => j.status === 'queued' || j.status === 'running')
      return active ? 2500 : false
    },
  })

  const createMut = useMutation({
    mutationFn: async (body: { kind: ConnectorKind; label: string; settings: object }) => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${knowledgeBaseId}/connectors`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify(body),
        },
      )
      const text = await res.text()
      if (!res.ok) throw new Error(text || res.statusText)
      return JSON.parse(text) as KnowledgeBaseConnector
    },
    onSuccess: () => {
      setLabel('')
      setSettingsText('{}')
      void qc.invalidateQueries({
        queryKey: queryKeys.knowledgeBaseConnectors(knowledgeBaseId),
      })
    },
  })

  const patchMut = useMutation({
    mutationFn: async (args: {
      connectorId: number
      body: { enabled?: boolean; label?: string; settings?: object }
    }) => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${knowledgeBaseId}/connectors/${args.connectorId}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify(args.body),
        },
      )
      const text = await res.text()
      if (!res.ok) throw new Error(text || res.statusText)
      return JSON.parse(text) as KnowledgeBaseConnector
    },
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: queryKeys.knowledgeBaseConnectors(knowledgeBaseId),
      })
    },
  })

  const syncMut = useMutation({
    mutationFn: async (connectorId: number) => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${knowledgeBaseId}/connectors/${connectorId}/sync`,
        { method: 'POST', headers: await getAuthHeaders() },
      )
      const text = await res.text()
      if (!res.ok) throw new Error(text || res.statusText)
      return JSON.parse(text) as ConnectorSyncJob
    },
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: queryKeys.knowledgeBaseConnectorJobs(knowledgeBaseId),
      })
    },
  })

  const deleteMut = useMutation({
    mutationFn: async (connectorId: number) => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${knowledgeBaseId}/connectors/${connectorId}`,
        { method: 'DELETE', headers: await getAuthHeaders() },
      )
      if (!res.ok) throw new Error(await res.text())
    },
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: queryKeys.knowledgeBaseConnectors(knowledgeBaseId),
      })
      void qc.invalidateQueries({
        queryKey: queryKeys.knowledgeBaseConnectorJobs(knowledgeBaseId),
      })
    },
  })

  const connectorLabelById = React.useMemo(() => {
    const m = new Map<number, string>()
    for (const c of connectorsQ.data ?? []) {
      const fallback = CONNECTOR_KIND_LABELS[c.kind as ConnectorKind] || c.kind
      m.set(c.id, c.label?.trim() ? c.label : fallback)
    }
    return m
  }, [connectorsQ.data])

  const submitConnector = (e: React.FormEvent) => {
    e.preventDefault()
    let settings: object = {}
    try {
      const parsed: unknown = JSON.parse(settingsText.trim() || '{}')
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return
      settings = parsed
    } catch {
      return
    }
    createMut.mutate({
      kind,
      label: label.trim(),
      settings,
    })
  }

  return (
    <>
      <section
        className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4 dark:border-neutral-800 dark:bg-neutral-900/40"
        aria-labelledby="kb-connectors-heading"
      >
        <h2
          id="kb-connectors-heading"
          className="mb-2 text-sm font-medium text-neutral-900 dark:text-neutral-100"
        >
          Connectors
        </h2>
        <p className="mb-4 text-xs text-neutral-600 dark:text-neutral-400">
          Register GitHub, GitLab, Confluence, or S3 sources for orchestrated sync jobs. File
          uploads below stay the fast path for local documents. Remote connectors run through the job
          queue (stubs today — pipeline is ready for real pull implementations).
        </p>

        <form className="mb-6 flex max-w-xl flex-col gap-3" onSubmit={submitConnector}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
              Type
              <Select
                className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                value={kind}
                onChange={(e) => setKind(e.target.value as ConnectorKind)}
              size="sm"
              inline
              >
                {CONNECTOR_KINDS.map((k) => (
                  <option
                    key={k}
                    value={k}
                    disabled={!isConnectorKindImplemented(k)}
                  >
                    {CONNECTOR_KIND_LABELS[k]}
                    {!isConnectorKindImplemented(k) ? ' (coming soon)' : ''}
                  </option>
                ))}
              </Select>
            </label>
            <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
              Label
              <input
                className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g. Product wiki"
                maxLength={255}
              />
            </label>
          </div>
          <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
            Settings (JSON)
            <textarea
              className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 font-mono text-xs dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
              rows={4}
              value={settingsText}
              onChange={(e) => setSettingsText(e.target.value)}
              spellCheck={false}
            />
          </label>
          {settingsJsonInvalid ? (
            <p className="text-xs text-red-600" role="alert">
              Invalid JSON in settings.
            </p>
          ) : null}
          {createMut.isError ? (
            <p className="text-xs text-red-600" role="alert">
              {(createMut.error as Error).message}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={createMut.isPending || settingsJsonInvalid}
            className="w-fit rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {createMut.isPending ? 'Adding…' : 'Add connector'}
          </button>
        </form>

        {connectorsQ.isPending && <PrismLogo state="loading" size={20} className="my-2" />}
        {connectorsQ.isError ? (
          <p className="text-sm text-red-600">{(connectorsQ.error as Error).message}</p>
        ) : null}
        {connectorsQ.data && connectorsQ.data.length === 0 ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">No connectors yet.</p>
        ) : null}
        {connectorsQ.data && connectorsQ.data.length > 0 ? (
          <ul className="space-y-3">
            {connectorsQ.data.map((c) => (
              <li
                key={c.id}
                className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-white/80 p-3 dark:border-neutral-700 dark:bg-neutral-950/60 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-neutral-900 dark:text-neutral-100">
                      {c.label || CONNECTOR_KIND_LABELS[c.kind as ConnectorKind] || c.kind}
                    </span>
                    <span className="rounded-full bg-neutral-200 px-2 py-0.5 text-xs text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
                      {CONNECTOR_KIND_LABELS[c.kind as ConnectorKind] || c.kind}
                    </span>
                  </div>
                  {Object.keys(c.settings).length > 0 ? (
                    <pre className="mt-1 max-h-20 overflow-auto text-[10px] text-neutral-500 dark:text-neutral-400">
                      {JSON.stringify(c.settings, null, 2)}
                    </pre>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-400">
                    <input
                      type="checkbox"
                      className="rounded border-neutral-400"
                      checked={c.enabled}
                      disabled={patchMut.isPending}
                      onChange={(e) =>
                        patchMut.mutate({
                          connectorId: c.id,
                          body: { enabled: e.target.checked },
                        })
                      }
                    />
                    Enabled
                  </label>
                  <button
                    type="button"
                    disabled={!c.enabled || syncMut.isPending}
                    className="inline-flex items-center gap-1 rounded-md border border-neutral-300 px-2 py-1 text-xs font-medium dark:border-neutral-600"
                    onClick={() => syncMut.mutate(c.id)}
                  >
                    <RefreshCw className="size-3.5" aria-hidden />
                    Sync now
                  </button>
                  <button
                    type="button"
                    className="rounded p-1 text-neutral-500 hover:bg-neutral-200 hover:text-red-600 dark:hover:bg-neutral-800 dark:hover:text-red-400"
                    title="Remove connector"
                    disabled={deleteMut.isPending}
                    onClick={() => {
                      if (window.confirm('Remove this connector and its future sync jobs?')) {
                        deleteMut.mutate(c.id)
                      }
                    }}
                  >
                    <Trash2 className="size-4" aria-hidden />
                    <span className="sr-only">Remove</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
        {patchMut.isError ? (
          <p className="mt-2 text-xs text-red-600">{(patchMut.error as Error).message}</p>
        ) : null}
        {syncMut.isError ? (
          <p className="mt-2 text-xs text-red-600">{(syncMut.error as Error).message}</p>
        ) : null}
        {deleteMut.isError ? (
          <p className="mt-2 text-xs text-red-600">{(deleteMut.error as Error).message}</p>
        ) : null}
      </section>

      <section aria-labelledby="kb-jobs-heading">
        <h2 id="kb-jobs-heading" className="mb-2 text-sm font-medium text-neutral-900 dark:text-neutral-100">
          Sync jobs
        </h2>
        <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
          Recent connector sync runs (queued → running → finished).
        </p>
        {jobsQ.isPending && <PrismLogo state="loading" size={20} className="my-2" />}
        {jobsQ.isError ? (
          <p className="text-sm text-red-600">{(jobsQ.error as Error).message}</p>
        ) : null}
        {jobsQ.data && jobsQ.data.length === 0 ? (
          <p className="text-sm text-neutral-500">No jobs yet — run &quot;Sync now&quot; on a connector.</p>
        ) : null}
        {jobsQ.data && jobsQ.data.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
            <table className="w-full min-w-[28rem] text-left text-sm">
              <thead className="border-b border-neutral-200 bg-neutral-50 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900/80 dark:text-neutral-400">
                <tr>
                  <th className="px-3 py-2 font-medium">ID</th>
                  <th className="px-3 py-2 font-medium">Connector</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                {jobsQ.data.map((j) => (
                  <tr key={j.id}>
                    <td className="px-3 py-2 font-mono text-xs text-neutral-600 dark:text-neutral-400">
                      {j.id}
                    </td>
                    <td className="px-3 py-2 text-neutral-900 dark:text-neutral-100">
                      {connectorLabelById.get(j.connector_id) ?? `#${j.connector_id}`}
                    </td>
                    <td className="px-3 py-2">
                      <JobStatusBadge job={j} />
                    </td>
                    <td className="max-w-xs px-3 py-2 text-xs text-neutral-600 dark:text-neutral-400">
                      {j.error_message ? (
                        <span className="text-red-600 dark:text-red-400">{j.error_message}</span>
                      ) : (
                        <JobMetaHint meta={j.meta} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </>
  )
}

function JobStatusBadge({ job }: { job: ConnectorSyncJob }) {
  const s = job.status
  const cls =
    s === 'succeeded'
      ? 'text-green-700 dark:text-green-400'
      : s === 'failed'
        ? 'text-red-600 dark:text-red-400'
        : 'text-amber-700 dark:text-amber-400'
  return <span className={cls}>{s}</span>
}

function JobMetaHint({ meta }: { meta: Record<string, unknown> }) {
  const msg = typeof meta.message === 'string' ? meta.message : null
  const pending = meta.implementation === 'pending'
  if (pending && msg) {
    return <span className="text-amber-800 dark:text-amber-300">{msg}</span>
  }
  if (msg) return <span>{msg}</span>
  return <span className="text-neutral-400">—</span>
}
