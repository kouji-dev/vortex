import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'

const apiBase = (
  typeof import.meta.env.VITE_API_URL === 'string' &&
  import.meta.env.VITE_API_URL.length > 0
    ? import.meta.env.VITE_API_URL
    : 'http://127.0.0.1:8000'
).replace(/\/$/, '')

const authHeaders = (): HeadersInit => {
  const t = import.meta.env.VITE_DEV_TOKEN
  if (typeof t === 'string' && t.length > 0) {
    return { Authorization: `Bearer ${t}` }
  }
  return {}
}

type Assistant = {
  id: number
  name: string
  description: string
  visibility: string
}

export const Route = createFileRoute('/assistants/')({
  component: AssistantsCatalog,
})

function AssistantsCatalog() {
  const q = useQuery({
    queryKey: ['assistants'],
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/assistants`, {
        headers: authHeaders(),
      })
      if (res.status === 401) {
        throw new Error('401 — set VITE_DEV_TOKEN=devtoken in frontend/.env')
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<Assistant[]>
    },
  })

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <h1 className="text-2xl font-semibold">Assistants</h1>
      {q.isPending && <p>Loading…</p>}
      {q.isError && (
        <p className="text-red-600">{(q.error as Error).message}</p>
      )}
      {q.isSuccess && q.data.length === 0 && (
        <p className="text-neutral-600">No assistants yet.</p>
      )}
      <ul className="space-y-2">
        {q.isSuccess &&
          q.data.map((a) => (
            <li key={a.id}>
              <Link
                to="/assistants/$id"
                params={{ id: String(a.id) }}
                className="text-blue-600 hover:underline font-medium"
              >
                {a.name}
              </Link>
              <span className="text-neutral-500 text-sm ml-2">({a.visibility})</span>
            </li>
          ))}
      </ul>
    </div>
  )
}
