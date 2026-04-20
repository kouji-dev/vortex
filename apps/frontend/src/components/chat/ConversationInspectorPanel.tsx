import { useConversationsOutlet } from '~/contexts/ConversationsOutletContext'

export function ConversationInspectorPanel() {
  const { activeMessage } = useConversationsOutlet()

  const isLlmCall = activeMessage?.kind === 'llm_call'
  const totalTokens =
    isLlmCall && activeMessage
      ? (activeMessage.data.input_tokens ?? 0) +
        (activeMessage.data.output_tokens ?? 0)
      : null
  const cost =
    isLlmCall && activeMessage?.cost_usd != null
      ? parseFloat(activeMessage.cost_usd)
      : null

  return (
    <aside className="run-inspect" data-testid="conversation-inspector">
      <div className="inspect-sec">
        <h4>Item</h4>
        <div className="kv">
          <div className="k">ID</div>
          <div className="v">{activeMessage?.id ?? '—'}</div>
          <div className="k">Kind</div>
          <div className="v">{activeMessage?.kind ?? '—'}</div>
          <div className="k">Role</div>
          <div className="v">{activeMessage?.role ?? '—'}</div>
          <div className="k">Tokens</div>
          <div className="v">{totalTokens != null ? String(totalTokens) : '—'}</div>
          <div className="k">Cost</div>
          <div className="v">
            {cost != null ? `$${cost.toFixed(5)}` : '—'}
          </div>
        </div>
      </div>
      <div className="inspect-sec">
        <h4>Tool calls</h4>
        {/* Backend does not yet surface per-message tool traces */}
        <p className="text-xs" style={{ color: 'var(--ink-3)' }}>No trace data exposed yet.</p>
      </div>
      <div className="inspect-sec">
        <h4>Retrieval hits</h4>
        {/* Wire to KB hit data once API exposes it per message */}
        <p className="text-xs" style={{ color: 'var(--ink-3)' }}>No retrieval data exposed yet.</p>
      </div>
    </aside>
  )
}
