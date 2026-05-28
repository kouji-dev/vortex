import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/admin/scim')({
  component: () => <div data-testid="admin-scim-placeholder" />,
})
