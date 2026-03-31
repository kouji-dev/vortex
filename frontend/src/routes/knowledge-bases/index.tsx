import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { Library, Plus } from 'lucide-react'
import * as React from 'react'

import { CreateKnowledgeBaseDialog } from '~/components/knowledge-bases/CreateKnowledgeBaseDialog'
import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  knowledgeBaseListFromResponse,
  parseKnowledgeBasesListJson,
} from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

export const Route = createFileRoute('/knowledge-bases/')({
  component: KnowledgeBasesIndexPage,
})

function KnowledgeBasesIndexPage() {
  const apiBase = getApiBase()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = React.useState(false)

  const listQ = useQuery({
    queryKey: queryKeys.knowledgeBases(),
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/knowledge-bases`, {
        headers: await getAuthHeaders(),
      })
      const text = await res.text()
      return knowledgeBaseListFromResponse(res, text, parseKnowledgeBasesListJson)
    },
  })

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 sm:p-6">
      <header className="flex flex-col gap-3 border-b border-neutral-200 pb-3 sm:flex-row sm:items-start sm:justify-between dark:border-neutral-800">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            <Library className="size-5 shrink-0 text-neutral-600 dark:text-neutral-400" aria-hidden />
            Knowledge bases
          </h1>
          <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
            Create corpora, upload documents, then attach bases to a chat for RAG.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
        >
          <Plus className="size-4" aria-hidden />
          Add knowledge base
        </button>
      </header>

      <CreateKnowledgeBaseDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(kb, meta) => {
          void navigate({
            to: '/knowledge-bases/$id',
            params: { id: String(kb.id) },
            ...(meta?.ingestWarning
              ? { state: { kbIngestWarning: meta.ingestWarning } }
              : {}),
          })
        }}
      />

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
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            None yet — use <span className="font-medium text-neutral-700 dark:text-neutral-300">Add knowledge base</span>.
          </p>
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
