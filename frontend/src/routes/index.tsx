import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

import { authorizedFetch } from '~/lib/authorizedFetch'

const apiBase = (
  typeof import.meta.env.VITE_API_URL === 'string' &&
  import.meta.env.VITE_API_URL.length > 0
    ? import.meta.env.VITE_API_URL
    : 'http://127.0.0.1:8000'
).replace(/\/$/, '')

export const Route = createFileRoute('/')({
  component: Home,
})

function Home() {
  const health = useQuery({
    queryKey: ['health', apiBase],
    queryFn: async () => {
      const res = await fetch(`${apiBase}/health`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      return res.json() as Promise<{ status: string }>
    },
  })

  const me = useQuery({
    queryKey: ['me', apiBase],
    queryFn: async () => {
      const res = await authorizedFetch(`${apiBase}/api/me`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      return res.json() as Promise<{ id: number; email: string; roles: string[] }>
    },
  })

  return (
    <div className="p-2 space-y-2">
      <h3 className="text-xl font-semibold">AI Portal</h3>
      <p className="text-sm text-neutral-600">
        Backend{' '}
        <code className="rounded bg-neutral-100 px-1 dark:bg-neutral-800">
          {apiBase}/health
        </code>
      </p>
      {health.isPending && <p>Checking API…</p>}
      {health.isError && (
        <p className="text-red-600">
          API unreachable: {(health.error as Error).message}
        </p>
      )}
      {health.isSuccess && (
        <p className="text-green-700 dark:text-green-400">
          API status: <strong>{health.data.status}</strong>
        </p>
      )}
      <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
        Signed-in profile{' '}
        <code className="rounded bg-neutral-100 px-1 dark:bg-neutral-800">
          GET /api/me
        </code>
      </p>
      {me.isPending && <p>Loading profile…</p>}
      {me.isError && (
        <p className="text-amber-700 dark:text-amber-400">
          /api/me: {(me.error as Error).message}
        </p>
      )}
      {me.isSuccess && (
        <p className="text-sm text-neutral-800 dark:text-neutral-200">
          <strong>{me.data.email}</strong> (id {me.data.id})
          {me.data.roles.length > 0 && (
            <span> — roles: {me.data.roles.join(', ')}</span>
          )}
        </p>
      )}
    </div>
  )
}
