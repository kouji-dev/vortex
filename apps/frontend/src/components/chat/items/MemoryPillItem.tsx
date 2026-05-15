import { Brain } from 'lucide-react'

import type { ThreadItem } from '~/lib/chat-types'

type Props = { item: ThreadItem & { kind: 'memory_pill' } }

export function MemoryPillItem({ item }: Props) {
  const n = item.data.count
  return (
    <div
      data-testid="memory-pill-item"
      className="inline-flex items-center gap-1 rounded-full border border-[color:var(--line)] bg-[color:var(--bg-2)] px-2 py-0.5 text-[11px]"
      style={{ color: 'var(--ink-2)' }}
    >
      <Brain className="size-3 opacity-70" strokeWidth={2} />
      <span>
        {n} {n === 1 ? 'memory injected' : 'memories injected'}
      </span>
    </div>
  )
}
