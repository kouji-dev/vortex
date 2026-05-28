import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/admin/data')({
  component: () => <div data-testid="admin-data-placeholder" />,
})
