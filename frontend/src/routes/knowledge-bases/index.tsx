import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { Library } from 'lucide-react'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { KnowledgeBaseSummary } from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

export const Route = createFileRoute('/knowledge-bases/')({
  component: KnowledgeBasesIndexPage,
})

function KnowledgeBasesIndexPage() {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')

  const listQ = useQuery({
    queryKey: queryKeys.knowledgeBases(),
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/knowledge-bases`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<KnowledgeBaseSummary[]>
    },
  })

  const createMut = useMutation({
    mutationFn: async (body: { name: string; description: string }) => {
      const res = await fetch(`${apiBase}/api/knowledge-bases`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<KnowledgeBaseSummary>
    },
    onSuccess: () => {
      setName('')
      setDescription('')
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBases() })
    },
  })

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 sm:p-6">
      <header className="flex flex-col gap-1 border-b border-neutral-200 pb-3 dark:border-neutral-800">
        <h1 className="flex items-center gap-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          <Library className="size-5 shrink-0 text-neutral-600 dark:text-neutral-400" aria-hidden />
          Knowledge bases
        </h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Create corpora, upload documents, then attach bases to a chat for RAG.
        </p>
      </header>

      <section
        className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-4 dark:border-neutral-800 dark:bg-neutral-900/40"
        aria-labelledby="kb-create-heading"
      >
        <h2 id="kb-create-heading" className="mb-3 text-sm font-medium text-neutral-900 dark:text-neutral-100">
          New knowledge base
        </h2>
        <form
          className="flex flex-col gap-3 sm:max-w-md"
          onSubmit={(e) => {
            e.preventDefault()
            const n = name.trim()
            if (!n || createMut.isPending) return
            createMut.mutate({ name: n, description: description.trim() })
          }}
        >
          <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
            Name
            <input
              className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={255}
              required
            />
          </label>
          <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
            Description (optional)
            <textarea
              className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={10_000}
            />
          </label>
          {createMut.isError && (
            <p className="text-sm text-red-600" role="alert">
              {(createMut.error as Error).message}
            </p>
          )}
          <button
            type="submit"
            disabled={createMut.isPending || !name.trim()}
            className="w-fit rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {createMut.isPending ? 'Creating…' : 'Create'}
          </button>
        </form>
      </section>

      <section aria-labelledby="kb-list-heading">
        <h2 id="kb-list-heading" className="mb-2 text-sm font-medium text-neutral-900 dark:text-neutral-100">
          Your knowledge bases
        </h2>
        {listQ.isPending && <p className="text-sm text-neutral-500">Loading…</p>}
        {listQ.isError && (
          <p className="text-sm text-red-600" role="alert">
            {(listQ.error as Error).message}
          </p>
        )}
        {listQ.data && listQ.data.length === 0 && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">None yet — create one above.</p>
        )}
        {listQ.data && listQ.data.length > 0 && (
          <ul className="divide-y divide-neutral-200 rounded-xl border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {listQ.data.map((kb) => (
              <li key={kb.id}>
                <Link
                  to="/knowledge-bases/$id"
                  params={{ id: String(kb.id) }}
                  className="block px-4 py-3 transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-800/80"
                >
                  <span className="font-medium text-neutral-900 dark:text-neutral-100">{kb.name}</span>
                  {kb.description ? (
                    <p className="mt-0.5 line-clamp-2 text-xs text-neutral-600 dark:text-neutral-400">
                      {kb.description}
                    </p>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
