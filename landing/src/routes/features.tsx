import { createFileRoute, Link } from '@tanstack/react-router'
import { getAppUrl } from '~/lib/app-url'

export const Route = createFileRoute('/features')({
  component: FeaturesPage,
})

const SECTIONS = [
  {
    icon: '💬',
    title: 'Streaming chat with any LLM',
    description:
      'Connect to OpenAI, Anthropic, or any OpenAI-compatible endpoint. Switch models per conversation. Responses stream token by token so your team never waits.',
    bullets: [
      'GPT-4o, Claude 3, and any compatible API',
      'Per-conversation model selection',
      'Streaming responses with markdown rendering',
      'Configurable system prompts via assistants',
    ],
  },
  {
    icon: '📚',
    title: 'Knowledge bases & RAG',
    description:
      'Upload PDFs, text files, and documents. AI Portal ingests them into a private vector store and retrieves relevant context automatically when you chat.',
    bullets: [
      'PDF, plain text, and markdown support',
      'Hybrid BM25 + vector retrieval with reranking',
      'Attach multiple knowledge bases per conversation',
      'Citation chips show which documents were used',
    ],
  },
  {
    icon: '🧠',
    title: 'Persistent memory',
    description:
      'The portal extracts preferences and facts from your conversations and reuses them automatically — so you never have to repeat yourself.',
    bullets: [
      'Automatic extraction from conversations',
      'Manual memory management via the Memories page',
      'Per-user, private memories',
      'Conversation summarization for long threads',
    ],
  },
  {
    icon: '🏢',
    title: 'Organizations & teams',
    description:
      'Invite your team, assign roles, and share assistants and knowledge bases at the org level. Self-hosted deployments get a single-org setup wizard.',
    bullets: [
      'Owner, admin, and member roles',
      'Invite members by email',
      'Shared assistants and knowledge bases',
      'Self-hosted single-org mode for enterprises',
    ],
  },
  {
    icon: '🔐',
    title: 'Auth & access control',
    description:
      'Email/password with verification out of the box. Portal API keys let you integrate AI Portal into your own tools and scripts.',
    bullets: [
      'Email + password with verification flow',
      'Portal API keys (aip_…) for programmatic access',
      'Role-based access control on all resources',
      'SSO via OAuth2 (Google, GitHub) — coming soon',
    ],
  },
  {
    icon: '🚀',
    title: 'Self-hosted or SaaS',
    description:
      'Deploy on Render in one click, or run it on your own infrastructure. One codebase, two modes — SaaS for teams, self-hosted for enterprises.',
    bullets: [
      'One-click Render deployment with render.yaml',
      'Supabase or any Postgres + pgvector database',
      'Docker Compose for local development',
      'Self-hosted mode with setup wizard',
    ],
  },
]

function FeaturesPage() {
  return (
    <div className="py-16">
      <div className="mx-auto max-w-4xl px-6">
        <div className="text-center mb-20">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white">Features</h1>
          <p className="mt-4 text-xl text-gray-600 dark:text-gray-400">
            Everything you need to run private AI for your team.
          </p>
        </div>

        <div className="space-y-20">
          {SECTIONS.map((s, i) => (
            <div
              key={s.title}
              className={`flex flex-col gap-10 lg:flex-row lg:items-start ${
                i % 2 === 1 ? 'lg:flex-row-reverse' : ''
              }`}
            >
              <div className="flex-1">
                <div className="text-4xl mb-4">{s.icon}</div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">{s.title}</h2>
                <p className="text-gray-600 dark:text-gray-400 leading-relaxed mb-6">
                  {s.description}
                </p>
                <ul className="space-y-2">
                  {s.bullets.map((b) => (
                    <li key={b} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
                      <span className="mt-0.5 text-indigo-500 font-bold">✓</span>
                      {b}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex-1 rounded-2xl border border-gray-100 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 min-h-48 flex items-center justify-center">
                <span className="text-6xl opacity-20">{s.icon}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-24 text-center">
          <a
            href={`${getAppUrl()}/register`}
            className="rounded-xl bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            Get started for free
          </a>
        </div>
      </div>
    </div>
  )
}
