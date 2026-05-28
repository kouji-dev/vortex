import { createFileRoute, redirect } from '@tanstack/react-router'

// /admin → /admin/members
export const Route = createFileRoute('/admin/')({
  beforeLoad: () => {
    throw redirect({ to: '/admin/members' })
  },
})
