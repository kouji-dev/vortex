import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { ArrowLeft, Trash2 } from 'lucide-react'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { KnowledgeBaseDocument, KnowledgeBaseSummary } from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

export const Route = createFileRoute('/knowledge-bases/$id')({
  component: KnowledgeBaseDetailPage,
})

function KnowledgeBaseDetailPage() {
  const { id: idParam } = Route.useParams()
  const kbId = Number(idParam)
  const apiBase = getApiBase()
  const qc = useQueryClient()
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
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<KnowledgeBaseDocument[]>
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
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kbId) })
      if (fileRef.current) fileRef.current.value = ''
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
                disabled={
                  patchMut.isPending ||
                  (editName.trim() === kbQ.data.name &&
                    (editDescription.trim() || '') === (kbQ.data.description || ''))
                }
                className="w-fit rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium dark:border-neutral-600"
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

          <section aria-labelledby="kb-upload-heading">
            <h2 id="kb-upload-heading" className="mb-2 text-sm font-medium text-neutral-900 dark:text-neutral-100">
              Upload documents
            </h2>
            <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
              .txt, .md, .pdf — ingest runs on the server (may take a moment).
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
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
