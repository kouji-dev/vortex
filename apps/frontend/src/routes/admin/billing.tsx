import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/admin/billing')({
  component: () => <div data-testid="admin-billing-placeholder" />,
})
