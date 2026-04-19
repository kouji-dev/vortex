import { useConversationsOutlet } from '~/contexts/ConversationsOutletContext'

export function ConversationInspectorPanel() {
  const { activeMessage } = useConversationsOutlet()
  return (
    <aside className="run-inspect" data-testid="conversation-inspector">
      <div className="inspect-sec">
        <h4>Message</h4>
        <div className="kv">
          <div className="k">ID</div>
          <div className="v">{activeMessage?.id ?? '—'}</div>
          <div className="k">Role</div>
          <div className="v">{activeMessage?.role ?? '—'}</div>
          <div className="k">Tokens</div>
          <div className="v">
            {activeMessage?.extra?.usage
              ? String(
                  (activeMessage.extra.usage.input_tokens ?? 0) +
                  (activeMessage.extra.usage.output_tokens ?? 0),
                )
              : '—'}
          </div>
          <div className="k">Cost</div>
          <div className="v">{activeMessage?.extra?.usage?.cost_usd != null ? `$${Number(activeMessage.extra.usage.cost_usd).toFixed(5)}` : '—'}</div>
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
