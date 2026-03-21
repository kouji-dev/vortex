import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'

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
    </div>
  )
}
