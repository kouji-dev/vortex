/**
 * Chat feature area. `/chat` redirects to `/chat/conversations` (composer + list);
 * after the first message, the thread is at `/chat/conversations/$id`.
 */
import { createFileRoute, Outlet, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/chat')({
  beforeLoad: ({ location }) => {
    const p = location.pathname.replace(/\/$/, '') || '/'
    if (p === '/chat') throw redirect({ to: '/chat/conversations' })
  },
  component: ChatLayout,
})

function ChatLayout() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <Outlet />
    </div>
  )
}
