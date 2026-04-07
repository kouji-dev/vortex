import { useInfiniteQuery } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { Eye, Library, Plus, Search } from 'lucide-react'
import * as React from 'react'

import { CreateKnowledgeBaseDialog } from '~/components/knowledge-bases/CreateKnowledgeBaseDialog'
import { TableShell } from '~/components/ui/TableShell'
import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import type { KnowledgeBaseSummary } from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

export const Route = createFileRoute('/knowledge-bases/')({
  component: KnowledgeBasesIndexPage,
})

function KnowledgeBasesIndexPage() {
  const apiBase = getApiBase()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = React.useState(false)
  const [search, setSearch] = React.useState('')

  const listQ = useInfiniteQuery({
    queryKey: queryKeys.knowledgeBasesPage(),
    initialPageParam: null as number | null,
    queryFn: async ({ pageParam }) => {
      const qs = new URLSearchParams({ limit: '25' })
      if (pageParam != null) qs.set('cursor', String(pageParam))
      const res = await fetch(`${apiBase}/api/knowledge-bases/page?${qs.toString()}`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json() as Promise<{
        items: KnowledgeBaseSummary[]
        next_cursor: number | null
      }>
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  })
  const rows = React.useMemo(
    () => listQ.data?.pages.flatMap((p) => p.items) ?? [],
    [listQ.data],
  )
  const filteredRows = React.useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((kb) => {
      const name = kb.name.toLowerCase()
      const desc = (kb.description ?? '').toLowerCase()
      return name.includes(q) || desc.includes(q)
    })
  }, [rows, search])
  const loadMoreDesktopRef = React.useRef<HTMLDivElement | null>(null)
  const loadMoreMobileRef = React.useRef<HTMLDivElement | null>(null)
  const tableScrollRef = React.useRef<HTMLDivElement | null>(null)

  React.useEffect(() => {
    const maybeFetch = () => {
      if (listQ.hasNextPage && !listQ.isFetchingNextPage) {
        void listQ.fetchNextPage()
      }
    }
    const observers: IntersectionObserver[] = []

    const mobileEl = loadMoreMobileRef.current
    if (mobileEl) {
      const obs = new IntersectionObserver(
        (entries) => {
          if (entries.some((e) => e.isIntersecting)) maybeFetch()
        },
        { root: null, rootMargin: '200px' },
      )
      obs.observe(mobileEl)
      observers.push(obs)
    }

    const desktopEl = loadMoreDesktopRef.current
    const scrollRoot = tableScrollRef.current
    if (desktopEl && scrollRoot) {
      const obs = new IntersectionObserver(
        (entries) => {
          if (entries.some((e) => e.isIntersecting)) maybeFetch()
        },
        { root: scrollRoot, rootMargin: '200px' },
      )
      obs.observe(desktopEl)
      observers.push(obs)
    }

    return () => observers.forEach((o) => o.disconnect())
  }, [listQ])

  const formatBytes = (bytes: number | undefined) => {
    if (bytes == null) return '—'
    if (bytes <= 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let value = bytes
    let i = 0
    while (value >= 1024 && i < units.length - 1) {
      value /= 1024
      i += 1
    }
    return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
  }

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
    })
  }

  const totalSize = rows.reduce((acc, kb) => acc + (kb.size_bytes ?? 0), 0)
  const totalChunks = rows.reduce((acc, kb) => acc + (kb.chunks_count ?? 0), 0)
  const totalDocs = rows.reduce((acc, kb) => acc + (kb.document_count ?? 0), 0)

  return (
    <div className="page-enter mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col gap-4 overflow-hidden p-4 sm:p-6">
      <header>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
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
        </div>
      </header>

      {rows.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
            KBs: <span className="font-semibold tabular-nums">{rows.length}</span>
          </span>
          <span className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
            Docs: <span className="font-semibold tabular-nums">{totalDocs.toLocaleString()}</span>
          </span>
          <span className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
            Chunks: <span className="font-semibold tabular-nums">{totalChunks.toLocaleString()}</span>
          </span>
          <span className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-neutral-600 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
            Size: <span className="font-semibold tabular-nums">{formatBytes(totalSize)}</span>
          </span>
        </div>
      )}

      <CreateKnowledgeBaseDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(kb) => {
          void navigate({
            to: '/knowledge-bases/$id',
            params: { id: String(kb.id) },
          })
        }}
      />

      <section aria-labelledby="kb-list-heading" className="flex min-h-0 flex-1 flex-col">
        <h2 id="kb-list-heading" className="mb-2 text-sm font-medium text-neutral-900 dark:text-neutral-100">
          Your knowledge bases
        </h2>
        <div className="mb-2 flex items-center gap-2 rounded-lg border border-neutral-200 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950">
          <Search className="size-4 shrink-0 text-neutral-400" aria-hidden />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search knowledge bases..."
            className="min-w-0 flex-1 bg-transparent text-sm text-neutral-900 placeholder-neutral-400 outline-none dark:text-neutral-100"
            aria-label="Search knowledge bases"
          />
        </div>
        {listQ.isPending && <p className="text-sm text-neutral-500">Loading…</p>}
        {listQ.isError && (
          <p className="text-sm text-red-600" role="alert">
            {(listQ.error as Error).message}
          </p>
        )}
        {!listQ.isPending && rows.length === 0 && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            None yet — use <span className="font-medium text-neutral-700 dark:text-neutral-300">Add knowledge base</span>.
          </p>
        )}
        {!listQ.isPending && rows.length > 0 && filteredRows.length === 0 && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">No knowledge bases match your search.</p>
        )}
        {filteredRows.length > 0 && (
          <>
            <div className="flex flex-col gap-2 md:hidden">
              {filteredRows.map((kb) => (
                <Link
                  key={kb.id}
                  to="/knowledge-bases/$id"
                  params={{ id: String(kb.id) }}
                  className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-neutral-900 dark:text-neutral-100">{kb.name}</p>
                      {kb.description ? (
                        <p className="mt-0.5 line-clamp-2 text-xs text-neutral-600 dark:text-neutral-400">
                          {kb.description}
                        </p>
                      ) : null}
                    </div>
                    <Eye className="mt-0.5 size-4 shrink-0 text-neutral-400" aria-hidden />
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-neutral-500 dark:text-neutral-400">
                    <span>{(kb.document_count ?? 0).toLocaleString()} docs</span>
                    <span>{(kb.chunks_count ?? 0).toLocaleString()} chunks</span>
                    <span>{formatBytes(kb.size_bytes)}</span>
                    <span>{formatDate(kb.created_at)}</span>
                  </div>
                </Link>
              ))}
              <div ref={loadMoreMobileRef} className="h-1" />
            </div>
            {listQ.isFetchingNextPage && (
              <p className="px-0 py-2 text-xs text-neutral-500 md:hidden">Loading more...</p>
            )}
            <div className="hidden md:flex md:min-h-0 md:flex-1 md:flex-col">
              <TableShell containerRef={tableScrollRef}>
                <table className="w-full min-w-[48rem] text-left text-sm">
                  <thead className="sticky top-0 z-10 border-b border-neutral-200 bg-neutral-50 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
                    <tr>
                      <th className="px-4 py-2 font-medium">Name</th>
                      <th className="px-4 py-2 text-right font-medium">Size</th>
                      <th className="px-4 py-2 text-right font-medium">Chunks</th>
                      <th className="px-4 py-2 font-medium">Created</th>
                      <th className="px-4 py-2 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                    {filteredRows.map((kb) => (
                      <tr key={kb.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-900/60">
                        <td className="px-4 py-2.5">
                          <Link
                            to="/knowledge-bases/$id"
                            params={{ id: String(kb.id) }}
                            className="block"
                          >
                            <div className="font-medium text-neutral-900 dark:text-neutral-100">{kb.name}</div>
                            <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                              {kb.description ? (
                                <p className="line-clamp-1 text-xs text-neutral-600 dark:text-neutral-400">
                                  {kb.description}
                                </p>
                              ) : null}
                              <span className="rounded-full border border-neutral-200 bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
                                {(kb.document_count ?? 0).toLocaleString()} docs
                              </span>
                            </div>
                          </Link>
                        </td>
                        <td className="px-4 py-2.5 text-right font-medium tabular-nums text-neutral-700 dark:text-neutral-300">
                          {formatBytes(kb.size_bytes)}
                        </td>
                        <td className="px-4 py-2.5 text-right font-medium tabular-nums text-neutral-700 dark:text-neutral-300">
                          {(kb.chunks_count ?? 0).toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-neutral-700 dark:text-neutral-300">
                          {formatDate(kb.created_at)}
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <Link
                            to="/knowledge-bases/$id"
                            params={{ id: String(kb.id) }}
                            className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-neutral-300 text-neutral-700 transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                            title="View knowledge base"
                            aria-label={`View ${kb.name}`}
                          >
                            <Eye className="size-3.5" aria-hidden />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div ref={loadMoreDesktopRef} className="h-1" />
                {listQ.isFetchingNextPage && (
                  <p className="px-4 py-2 text-xs text-neutral-500">Loading more...</p>
                )}
              </TableShell>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
