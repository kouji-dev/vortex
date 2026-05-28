import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/admin/webhooks')({
  component: () => <div data-testid="admin-webhooks-placeholder" />,
})
