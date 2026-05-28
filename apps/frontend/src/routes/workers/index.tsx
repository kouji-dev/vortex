/**
 * /workers — placeholder index. The layout redirects to /workers/tasks so
 * this route is rarely rendered, but kept for routing completeness.
 */
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/workers/')({
  component: WorkersIndex,
})

function WorkersIndex() {
  return (
    <div className="panel" style={{ padding: 16, fontSize: 12, color: 'var(--ink-3)' }}>
      Redirecting to tasks…
    </div>
  )
}
