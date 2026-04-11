import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useLocation, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, Trash2 } from 'lucide-react'
import * as React from 'react'
import { PrismLogo } from '~/components/brand'

import { KnowledgeBaseConnectorsSection } from '~/components/knowledge-bases/KnowledgeBaseConnectorsSection'
import { useDocumentProgressQuery } from '~/hooks/useDocumentProgressQuery'
import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import { postFormDataWithUploadProgress } from '~/lib/postFormDataWithUploadProgress'
import {
  type KnowledgeBaseDocument,
  type KnowledgeBaseSummary,
  knowledgeBaseListFromResponse,
  parseKnowledgeBaseDocumentsListJson,
} from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'
import { cn } from '~/lib/utils'

export const Route = createFileRoute('/knowledge-bases/$id')({
  component: KnowledgeBaseDetailPage,
})

function useKbDocumentLive(kbId: number, docId: number, listStatus: string) {
  const qc = useQueryClient()
  const poll = listStatus === 'pending' || listStatus === 'ingesting'
  const { data, isPending } = useDocumentProgressQuery(kbId, docId, { enabled: poll })

  const prevStatus = React.useRef<string | undefined>(undefined)
  React.useEffect(() => {
    if (prevStatus.current === 'ingesting' && data?.status === 'ready') {
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kbId) })
    }
    if (data?.status === 'failed' && prevStatus.current !== 'failed') {
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kbId) })
    }
    prevStatus.current = data?.status
  }, [data?.status, kbId, qc])

  const displayStatus = poll && data?.status ? data.status : listStatus

  const percent =
    data && data.chunks_total != null && data.chunks_total > 0
      ? Math.min(100, Math.round((data.chunks_done / data.chunks_total) * 100))
      : null

  const showChunkUi = poll && data?.status === 'ingesting'
  const showQueued = poll && data?.status === 'pending'

  const statusClass =
    displayStatus === 'ready'
      ? 'text-green-700 dark:text-green-400'
      : displayStatus === 'failed'
        ? 'text-red-600 dark:text-red-400'
        : 'text-amber-700 dark:text-amber-400'

  return {
    displayStatus,
    statusClass,
    data,
    percent,
    showChunkUi,
    showQueued,
    poll,
    isPending,
  }
}

function KnowledgeBaseDocumentTableRow({
  kbId,
  doc,
  deleteDisabled,
  onDelete,
}: {
  kbId: number
  doc: KnowledgeBaseDocument
  deleteDisabled: boolean
  onDelete: () => void
}) {
  const live = useKbDocumentLive(kbId, doc.id, doc.status)

  const progressBody = (() => {
    if (live.showChunkUi) {
      return (
        <div className="flex flex-col gap-1.5" data-testid="kb-doc-chunk-progress">
          {live.percent !== null && live.data ? (
            <>
              <div className="flex items-center justify-between gap-2">
                <span
                  className="font-medium tabular-nums text-neutral-800 dark:text-neutral-200"
                  aria-label={`Indexing ${live.percent}% (${live.data.chunks_done} of ${live.data.chunks_total} chunks)`}
                >
                  {live.percent}%
                </span>
                <span className="tabular-nums text-neutral-500 dark:text-neutral-400">
                  {live.data.chunks_done}/{live.data.chunks_total} chunks
                </span>
              </div>
              <div
                className="h-2 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700"
                role="progressbar"
                aria-valuenow={live.data.chunks_done}
                aria-valuemin={0}
                aria-valuemax={live.data.chunks_total ?? undefined}
                aria-label="Chunks embedded"
              >
                <div
                  className="h-full bg-blue-500 transition-[width] duration-300 ease-out"
                  style={{ width: `${live.percent}%` }}
                />
              </div>
            </>
          ) : (
            <span className="flex items-center gap-1.5 text-neutral-500 dark:text-neutral-400">
              <PrismLogo state="loading" size={14} />
              Indexing…
            </span>
          )}
        </div>
      )
    }
    if (live.showQueued) {
      return (
        <p className="flex items-center gap-1.5 text-neutral-500 dark:text-neutral-400">
          <PrismLogo state="loading" size={14} />
          Queued for indexing…
        </p>
      )
    }
    if (doc.status === 'failed' || live.displayStatus === 'failed') {
      const errMsg = (doc.ingest_error ?? live.data?.ingest_error ?? '').trim()
      if (errMsg) {
        return (
          <p
            className="line-clamp-6 break-words text-red-600 dark:text-red-400"
            data-testid="kb-doc-ingest-error"
            title={errMsg}
          >
            {errMsg}
          </p>
        )
      }
      return (
        <span className="text-red-600 dark:text-red-400" data-testid="kb-doc-ingest-error">
          Ingest failed
        </span>
      )
    }
    if (live.poll && live.isPending && !live.data) {
      return (
        <span className="flex items-center gap-1.5 text-neutral-500 dark:text-neutral-400">
          <PrismLogo state="loading" size={14} />
          Loading…
        </span>
      )
    }
    return <span className="text-neutral-400 dark:text-neutral-600">—</span>
  })()

  return (
    <tr>
      <td className="px-3 py-2 text-neutral-900 dark:text-neutral-100">{doc.filename}</td>
      <td className="px-3 py-2 align-top">
        <span data-testid="kb-doc-status" className={cn('font-medium', live.statusClass)}>
          {live.displayStatus}
        </span>
      </td>
      <td className="min-w-48 max-w-64 px-3 py-2 align-top text-xs text-neutral-600 dark:text-neutral-400">
        {progressBody}
      </td>
      <td className="px-3 py-2 align-top">
        <button
          type="button"
          className="rounded p-1 text-neutral-500 hover:bg-neutral-200 hover:text-red-600 dark:hover:bg-neutral-800 dark:hover:text-red-400"
          title="Remove document"
          disabled={deleteDisabled}
          onClick={onDelete}
        >
          <Trash2 className="size-4" aria-hidden />
          <span className="sr-only">Remove</span>
        </button>
      </td>
    </tr>
  )
}

function KnowledgeBaseDetailPage() {
  const { id: idParam } = Route.useParams()
  const kbId = Number(idParam)
  const apiBase = getApiBase()
  const qc = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const [ingestBanner, setIngestBanner] = React.useState<string | null>(null)

  React.useEffect(() => {
    const w = location.state?.kbIngestWarning
    if (typeof w !== 'string' || !w.trim()) {
      return
    }
    setIngestBanner(w.trim())
    void navigate({
      to: '/knowledge-bases/$id',
      params: { id: idParam },
      replace: true,
      state: {},
    })
  }, [location.state?.kbIngestWarning, idParam, navigate])
  const fileRef = React.useRef<HTMLInputElement>(null)

  const kbQ = useQuery({
    queryKey: queryKeys.knowledgeBase(kbId),
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/knowledge-bases/${kbId}`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<KnowledgeBaseSummary>
    },
    enabled: Number.isFinite(kbId),
  })

  const docsQ = useQuery({
    queryKey: queryKeys.knowledgeBaseDocuments(kbId),
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/knowledge-bases/${kbId}/documents`, {
        headers: await getAuthHeaders(),
      })
      const text = await res.text()
      return knowledgeBaseListFromResponse(res, text, parseKnowledgeBaseDocumentsListJson)
    },
    enabled: Number.isFinite(kbId),
  })

  const [editName, setEditName] = React.useState('')
  const [editDescription, setEditDescription] = React.useState('')

  React.useEffect(() => {
    if (kbQ.data) {
      setEditName(kbQ.data.name)
      setEditDescription(kbQ.data.description ?? '')
    }
  }, [kbQ.data])

  const patchMut = useMutation({
    mutationFn: async (body: { name?: string; description?: string }) => {
      const res = await fetch(`${apiBase}/api/knowledge-bases/${kbId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<KnowledgeBaseSummary>
    },
    onSuccess: (data) => {
      void qc.setQueryData(queryKeys.knowledgeBase(kbId), data)
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBases() })
    },
  })

  type ActiveKbUpload = {
    id: string
    filename: string
    percent: number
    lengthComputable: boolean
    error?: string
  }
  const [activeUploads, setActiveUploads] = React.useState<ActiveKbUpload[]>([])

  const runKbDocumentUpload = React.useCallback(
    async (file: File) => {
      const uploadId =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? crypto.randomUUID()
          : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
              const r = (Math.random() * 16) | 0
              return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
            })
      setActiveUploads((prev) => [
        ...prev,
        {
          id: uploadId,
          filename: file.name,
          percent: 0,
          lengthComputable: false,
        },
      ])

      const fd = new FormData()
      fd.append('file', file)
      const url = `${apiBase}/api/knowledge-bases/${kbId}/documents`

      const dismissAfterMs = (ms: number) => {
        window.setTimeout(() => {
          setActiveUploads((prev) => prev.filter((u) => u.id !== uploadId))
        }, ms)
      }

      try {
        const headers = await getAuthHeaders()
        const uploadResult = await postFormDataWithUploadProgress(url, fd, headers, (percent, lengthComputable) => {
          setActiveUploads((prev) =>
            prev.map((u) =>
              u.id === uploadId ? { ...u, percent, lengthComputable } : u,
            ),
          )
        })
        const firstResult = uploadResult.results[0]
        if (firstResult?.document_id == null && firstResult?.ingest_error) {
          setActiveUploads((prev) =>
            prev.map((u) => (u.id === uploadId ? { ...u, error: firstResult.ingest_error! } : u)),
          )
          dismissAfterMs(8000)
          return
        }
        setActiveUploads((prev) =>
          prev.map((u) =>
            u.id === uploadId ? { ...u, percent: 100, lengthComputable: true } : u,
          ),
        )
        void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kbId) })
        dismissAfterMs(450)
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Upload failed'
        setActiveUploads((prev) =>
          prev.map((u) => (u.id === uploadId ? { ...u, error: message } : u)),
        )
        dismissAfterMs(8000)
      }
    },
    [apiBase, kbId, qc],
  )

  const deleteDocMut = useMutation({
    mutationFn: async (documentId: number) => {
      const res = await fetch(
        `${apiBase}/api/knowledge-bases/${kbId}/documents/${documentId}`,
        { method: 'DELETE', headers: await getAuthHeaders() },
      )
      if (!res.ok) throw new Error(await res.text())
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kbId) })
    },
  })

  if (!Number.isFinite(kbId)) {
    return <p className="p-4 text-sm text-red-600">Invalid knowledge base.</p>
  }

  const kb = kbQ.data
  const detailsDirty = Boolean(
    kb &&
      (editName.trim() !== kb.name ||
        (editDescription.trim() || '') !== (kb.description || '')),
  )
  const saveDisabled = patchMut.isPending || !detailsDirty

  return (
    <div className="page-enter flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 sm:p-6">
      <div className="flex items-center gap-2">
        <Link
          to="/knowledge-bases"
          className="inline-flex items-center gap-1 rounded-md text-sm text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
        >
          <ArrowLeft className="size-4" aria-hidden />
          All knowledge bases
        </Link>
      </div>

      {ingestBanner && (
        <div
          className="flex flex-col gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100"
          role="status"
        >
          <p className="font-medium">Initial upload did not finish ingesting</p>
          <p className="text-amber-900/90 dark:text-amber-100/90">{ingestBanner}</p>
          <button
            type="button"
            className="self-start text-sm font-medium text-amber-900 underline dark:text-amber-200"
            onClick={() => setIngestBanner(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {kbQ.isPending && <p className="text-sm text-neutral-500">Loading…</p>}
      {kbQ.isError && (
        <p className="text-sm text-red-600" role="alert">
          {(kbQ.error as Error).message}
        </p>
      )}

      {kbQ.data && (
        <>
          <header className="border-b border-neutral-200 pb-3 dark:border-neutral-800">
            <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              {kbQ.data.name}
            </h1>
            <p className="mt-1 text-xs text-neutral-500">
              Attach this base to a conversation under{' '}
              <Link to="/chat/conversations" className="text-blue-600 underline dark:text-blue-400">
                Chat
              </Link>{' '}
              → Knowledge bases.
            </p>
          </header>

          <section
            className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4 dark:border-neutral-800 dark:bg-neutral-900/40"
            aria-labelledby="kb-edit-heading"
          >
            <h2 id="kb-edit-heading" className="mb-3 text-sm font-medium text-neutral-900 dark:text-neutral-100">
              Details
            </h2>
            <div className="flex max-w-md flex-col gap-3">
              <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                Name
                <input
                  className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  maxLength={255}
                />
              </label>
              <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                Description
                <textarea
                  className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                  rows={2}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  maxLength={10_000}
                />
              </label>
              {patchMut.isError && (
                <p className="text-sm text-red-600">{(patchMut.error as Error).message}</p>
              )}
              <button
                type="button"
                disabled={saveDisabled}
                className={cn(
                  'w-fit rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-neutral-950',
                  patchMut.isPending &&
                    'cursor-wait border border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800/60 dark:bg-blue-950/40 dark:text-blue-200',
                  !patchMut.isPending &&
                    detailsDirty &&
                    'cursor-pointer border border-blue-600 bg-blue-600 text-white shadow-sm hover:border-blue-500 hover:bg-blue-500 focus-visible:ring-blue-500 dark:border-blue-500 dark:bg-blue-600 dark:hover:border-blue-400 dark:hover:bg-blue-500',
                  !patchMut.isPending &&
                    !detailsDirty &&
                    'cursor-not-allowed border border-neutral-200 bg-neutral-100 text-neutral-400 dark:border-neutral-700 dark:bg-neutral-800/90 dark:text-neutral-500',
                )}
                onClick={() =>
                  patchMut.mutate({
                    name: editName.trim(),
                    description: editDescription.trim(),
                  })
                }
              >
                {patchMut.isPending ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          </section>

          <KnowledgeBaseConnectorsSection knowledgeBaseId={kbId} />

          <section aria-labelledby="kb-upload-heading">
            <h2 id="kb-upload-heading" className="mb-2 text-sm font-medium text-neutral-900 dark:text-neutral-100">
              Upload documents (files connector)
            </h2>
            <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
              .txt, .md, .pdf — multiple files allowed. Upload finishes quickly; indexing runs in
              the background (pending, then ingesting with chunk progress, then ready or failed).
            </p>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
              data-testid="kb-upload-input"
              className="block text-sm text-neutral-600 file:mr-3 file:rounded-md file:border-0 file:bg-neutral-200 file:px-3 file:py-1.5 file:text-sm dark:text-neutral-400 dark:file:bg-neutral-800"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? [])
                e.target.value = ''
                for (const f of files) {
                  void runKbDocumentUpload(f)
                }
              }}
            />
            {activeUploads.length > 0 && (
              <ul
                data-testid="kb-upload-active"
                className="mt-3 space-y-2 rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-700 dark:bg-neutral-950/60"
                aria-label="Upload progress"
              >
                {activeUploads.map((u) => (
                  <li
                    key={u.id}
                    data-testid={`kb-upload-row-${u.id}`}
                    className="text-sm text-neutral-800 dark:text-neutral-200"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="min-w-0 truncate font-medium" title={u.filename}>
                        {u.filename}
                      </span>
                      {u.error ? (
                        <span className="text-red-600 dark:text-red-400">{u.error}</span>
                      ) : u.lengthComputable ? (
                        <span className="tabular-nums text-neutral-500 dark:text-neutral-400">
                          {u.percent}%
                        </span>
                      ) : (
                        <span className="flex items-center gap-1.5 text-neutral-500 dark:text-neutral-400">
                          <PrismLogo state="loading" size={14} />
                          Uploading…
                        </span>
                      )}
                    </div>
                    {!u.error && u.lengthComputable && (
                      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
                        <div
                          className="h-full bg-blue-500 transition-[width] duration-150 ease-out"
                          style={{ width: `${u.percent}%` }}
                        />
                      </div>
                    )}
                    {!u.error && !u.lengthComputable && (
                      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
                        <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-500" />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="kb-docs-heading">
            <h2 id="kb-docs-heading" className="mb-2 text-sm font-medium text-neutral-900 dark:text-neutral-100">
              Documents
            </h2>
            {docsQ.isPending && <p className="text-sm text-neutral-500">Loading…</p>}
            {docsQ.isError && (
              <p className="text-sm text-red-600">{(docsQ.error as Error).message}</p>
            )}
            {docsQ.data && docsQ.data.length === 0 && (
              <p className="text-sm text-neutral-500">No files yet.</p>
            )}
            {docsQ.data && docsQ.data.length > 0 && (
              <div className="overflow-x-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
                <table className="w-full min-w-[28rem] text-left text-sm">
                  <thead className="border-b border-neutral-200 bg-neutral-50 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900/80 dark:text-neutral-400">
                    <tr>
                      <th className="px-3 py-2 font-medium">File</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-3 py-2 font-medium">Progress</th>
                      <th className="w-12 px-3 py-2 font-medium" aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                    {docsQ.data.map((d) => (
                      <KnowledgeBaseDocumentTableRow
                        key={d.id}
                        kbId={kbId}
                        doc={d}
                        deleteDisabled={deleteDocMut.isPending}
                        onDelete={() => {
                          if (window.confirm(`Remove “${d.filename}” from this knowledge base?`)) {
                            deleteDocMut.mutate(d.id)
                          }
                        }}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {deleteDocMut.isError && (
              <p className="mt-2 text-sm text-red-600">{(deleteDocMut.error as Error).message}</p>
            )}
          </section>
        </>
      )}
    </div>
  )
}
