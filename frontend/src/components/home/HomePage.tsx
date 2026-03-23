import { useHealthQuery } from '~/hooks/useHealthQuery'
import { useMeQuery } from '~/hooks/useMeQuery'
import { ComingSoonCard } from '~/components/home/ComingSoonCard'
import { FeatureCard } from '~/components/home/FeatureCard'
import { SessionProfileCard } from '~/components/home/SessionProfileCard'
import { SystemStatusCard } from '~/components/home/SystemStatusCard'

export function HomePage() {
  const health = useHealthQuery()
  const me = useMeQuery()

  return (
    <div className="mx-auto min-h-0 w-full max-w-4xl flex-1 space-y-8 overflow-y-auto overscroll-contain p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
          Home
        </h1>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          Pick a feature or review connection and account status.
        </p>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-neutral-500">
          Features
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <FeatureCard
            to="/chat/conversations"
            title="Chat"
            description="Conversations with streaming replies, models from the catalog, and thread settings."
          />
          <ComingSoonCard
            title="More features"
            description="Additional modules will appear here as the portal grows."
          />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-neutral-500">
          Status
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <SystemStatusCard health={health} />
          <SessionProfileCard me={me} />
        </div>
      </section>
    </div>
  )
}
