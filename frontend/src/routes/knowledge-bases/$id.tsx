import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link, useLocation, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, Trash2 } from 'lucide-react'
import * as React from 'react'

import { KnowledgeBaseConnectorsSection } from '~/components/knowledge-bases/KnowledgeBaseConnectorsSection'
import { useDocumentProgressQuery } from '~/hooks/useDocumentProgressQuery'
import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
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

function DocumentProgressBar({ kbId, docId }: { kbId: number; docId: number }) {
  const qc = useQueryClient()
  const { data } = useDocumentProgressQuery(kbId, docId)

  const prevStatus = React.useRef<string | undefined>(undefined)
  React.useEffect(() => {
    if (prevStatus.current === 'ingesting' && data?.status === 'ready') {
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kbId) })
    }
    prevStatus.current = data?.status
  }, [data?.status, kbId, qc])

  if (!data || data.status !== 'ingesting') return null

  const percent =
    data.chunks_total && data.chunks_total > 0
      ? Math.round((data.chunks_done / data.chunks_total) * 100)
      : null

  return (
    <div className="mt-1 flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
      {percent !== null ? (
        <>
          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{ width: `${percent}%` }}
            />
          </div>
          <span>
            {data.chunks_done}/{data.chunks_total} chunks
          </span>
        </>
      ) : (
        <span className="animate-pulse">Indexing…</span>
      )}
    </div>
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

  const uploadMut = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch(`${apiBase}/api/knowledge-bases/${kbId}/documents`, {
        method: 'POST',
        headers: await getAuthHeaders(),
        body: fd,
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<{ document_id: number; status: string }>
    },
    onSuccess: () => {
      if (fileRef.current) fileRef.current.value = ''
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kbId) })
    },
  })

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
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 sm:p-6">
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
              .txt, .md, .pdf — ingest runs on the server immediately after upload (may take a moment).
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
              data-testid="kb-upload-input"
              className="block text-sm text-neutral-600 file:mr-3 file:rounded-md file:border-0 file:bg-neutral-200 file:px-3 file:py-1.5 file:text-sm dark:text-neutral-400 dark:file:bg-neutral-800"
              disabled={uploadMut.isPending}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) uploadMut.mutate(f)
              }}
            />
            {uploadMut.isError && (
              <p className="mt-2 text-sm text-red-600" role="alert">
                {(uploadMut.error as Error).message}
              </p>
            )}
            {uploadMut.isPending && <p className="mt-2 text-sm text-neutral-500">Uploading…</p>}
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
                <table className="w-full min-w-[20rem] text-left text-sm">
                  <thead className="border-b border-neutral-200 bg-neutral-50 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900/80 dark:text-neutral-400">
                    <tr>
                      <th className="px-3 py-2 font-medium">File</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="w-12 px-3 py-2 font-medium" aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                    {docsQ.data.map((d) => (
                      <tr key={d.id}>
                        <td className="px-3 py-2 text-neutral-900 dark:text-neutral-100">{d.filename}</td>
                        <td className="px-3 py-2">
                          <span
                            className={
                              d.status === 'ready'
                                ? 'text-green-700 dark:text-green-400'
                                : d.status === 'failed'
                                  ? 'text-red-600 dark:text-red-400'
                                  : 'text-amber-700 dark:text-amber-400'
                            }
                          >
                            {d.status}
                          </span>
                          {d.status === 'ingesting' && (
                            <DocumentProgressBar kbId={kbId} docId={d.id} />
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <button
                            type="button"
                            className="rounded p-1 text-neutral-500 hover:bg-neutral-200 hover:text-red-600 dark:hover:bg-neutral-800 dark:hover:text-red-400"
                            title="Remove document"
                            disabled={deleteDocMut.isPending}
                            onClick={() => {
                              if (window.confirm(`Remove “${d.filename}” from this knowledge base?`)) {
                                deleteDocMut.mutate(d.id)
                              }
                            }}
                          >
                            <Trash2 className="size-4" aria-hidden />
                            <span className="sr-only">Remove</span>
                          </button>
                        </td>
                      </tr>
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
