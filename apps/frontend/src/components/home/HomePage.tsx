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
    <div className="page-enter mx-auto min-h-0 w-full max-w-4xl flex-1 space-y-8 overflow-y-auto overscroll-contain p-4 md:p-6">
      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-ink-3">
          Features
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <FeatureCard
            to="/chat/conversations"
            title="Chat"
            description="Conversations with streaming replies, models from the catalog, and thread settings."
          />
          <FeatureCard
            to="/knowledge-bases"
            title="Knowledge bases"
            description="Corpora for RAG: connectors, uploads, and documents—attach bases to chats for grounded answers."
          />
          <FeatureCard
            to="/memories"
            title="Memories"
            description="Persistent facts the assistant remembers about you—auto-learned or manually added."
          />
          <ComingSoonCard
            title="More features"
            description="Additional modules will appear here as the portal grows."
          />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-ink-3">
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
