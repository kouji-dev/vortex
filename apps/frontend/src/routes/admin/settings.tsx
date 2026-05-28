import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/admin/settings')({
  component: () => <div data-testid="admin-settings-placeholder" />,
})
