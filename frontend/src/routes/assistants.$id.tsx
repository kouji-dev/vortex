import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import * as React from 'react'

import { getAuthHeaders } from '~/lib/authorizedFetch'

const apiBase = (
  typeof import.meta.env.VITE_API_URL === 'string' &&
  import.meta.env.VITE_API_URL.length > 0
    ? import.meta.env.VITE_API_URL
    : 'http://127.0.0.1:8000'
).replace(/\/$/, '')

type Assistant = {
  id: number
  name: string
  description: string
  system_prompt: string
}

export const Route = createFileRoute('/assistants/$id')({
  component: AssistantChat,
})

function AssistantChat() {
  const { id } = Route.useParams()
  const assistantId = Number(id)
  const qc = useQueryClient()
  const [input, setInput] = React.useState('')
  const [sessionId, setSessionId] = React.useState<number | null>(null)
  const [lines, setLines] = React.useState<{ role: string; text: string }[]>([])

  const assistantQ = useQuery({
    queryKey: ['assistant', assistantId],
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/assistants/${assistantId}`, {
        headers: await getAuthHeaders(),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<Assistant>
    },
    enabled: Number.isFinite(assistantId),
  })

  const send = useMutation({
    mutationFn: async (text: string) => {
      const body: Record<string, unknown> = {
        assistant_id: assistantId,
        messages: [{ role: 'user', content: text }],
        use_rag: true,
      }
      if (sessionId != null) body.session_id = sessionId
      const res = await fetch(`${apiBase}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const err = await res.text()
        throw new Error(err || `HTTP ${res.status}`)
      }
      return res.json() as Promise<{ session_id: number; reply: string }>
    },
    onSuccess: (data, text) => {
      setSessionId(data.session_id)
      setLines((prev) => [
        ...prev,
        { role: 'user', text },
        { role: 'assistant', text: data.reply },
      ])
      setInput('')
      void qc.invalidateQueries({ queryKey: ['assistant', assistantId] })
    },
  })

  if (!Number.isFinite(assistantId)) {
    return <p className="p-4">Invalid assistant id.</p>
  }

  return (
    <div className="p-4 max-w-2xl space-y-4">
      <Link to="/assistants" className="text-blue-600 text-sm hover:underline">
        ← Catalog
      </Link>
      {assistantQ.isPending && <p>Loading assistant…</p>}
      {assistantQ.isError && (
        <p className="text-red-600">{(assistantQ.error as Error).message}</p>
      )}
      {assistantQ.isSuccess && (
        <>
          <h1 className="text-2xl font-semibold">{assistantQ.data.name}</h1>
          <p className="text-neutral-600 text-sm">{assistantQ.data.description}</p>
        </>
      )}
      <div className="border rounded-lg p-3 min-h-[200px] space-y-2 bg-neutral-50 dark:bg-neutral-900">
        {lines.map((l, i) => (
          <div key={i} className="text-sm">
            <span className="font-semibold text-neutral-500">{l.role}: </span>
            <span className="whitespace-pre-wrap">{l.text}</span>
          </div>
        ))}
      </div>
      {send.isError && (
        <p className="text-red-600 text-sm">{(send.error as Error).message}</p>
      )}
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          const t = input.trim()
          if (t) send.mutate(t)
        }}
      >
        <input
          className="flex-1 border rounded px-3 py-2"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message…"
        />
        <button
          type="submit"
          className="px-4 py-2 rounded bg-neutral-800 text-white disabled:opacity-50"
          disabled={send.isPending}
        >
          Send
        </button>
      </form>
    </div>
  )
}
