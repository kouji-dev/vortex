import { createFileRoute } from '@tanstack/react-router'
import { ConsumptionPage } from '~/components/admin/ConsumptionPage'

export const Route = createFileRoute('/org/consumption')({
  component: ConsumptionPage,
})
