import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/gateway/')({
  beforeLoad: () => {
    throw redirect({ to: '/gateway/overview' })
  },
})
