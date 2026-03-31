import { createFileRoute } from '@tanstack/react-router'

import { MemoriesPage } from '~/components/memories/MemoriesPage'

export const Route = createFileRoute('/memories')({
  component: MemoriesPage,
})
