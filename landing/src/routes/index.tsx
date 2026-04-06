import { createFileRoute, Link } from '@tanstack/react-router'
import { getAppUrl } from '~/lib/app-url'

export const Route = createFileRoute('/')({
  component: HomePage,
})

const FEATURES = [
  {
    icon: '💬',
    title: 'Streaming chat',
    description:
      'Real-time conversations with any OpenAI-compatible or Anthropic model. Switch models per conversation.',
  },
  {
    icon: '📚',
    title: 'Knowledge bases',
    description:
      'Upload documents and let the AI answer questions grounded in your own data via hybrid RAG retrieval.',
  },
  {
    icon: '🧠',
    title: 'Memory',
    description:
      'The portal learns your preferences across conversations so context carries forward automatically.',
  },
  {
    icon: '🔐',
    title: 'Private by design',
    description:
      'Self-hosted or SaaS — your data never leaves your infrastructure. Full control over model routing.',
  },
  {
    icon: '🤝',
    title: 'Teams & orgs',
    description:
      'Invite members, share assistants, and manage knowledge bases at the organization level.',
  },
  {
    icon: '🔑',
    title: 'API keys',
    description:
      'Generate portal API keys to integrate AI Portal into your own apps and scripts.',
  },
]

function HomePage() {
  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden py-24 sm:py-32">
        <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-indigo-50 to-white dark:from-indigo-950/30 dark:to-gray-950" />
        <div className="mx-auto max-w-4xl px-6 text-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-4 py-1.5 text-sm font-medium text-indigo-700 dark:border-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-300">
            <span className="h-2 w-2 rounded-full bg-indigo-500" />
            Self-hosted AI for teams
          </div>
          <h1 className="text-5xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-6xl">
            Your team's private
            <br />
            <span className="text-indigo-600 dark:text-indigo-400">AI workspace</span>
          </h1>
          <p className="mt-6 text-xl text-gray-600 dark:text-gray-400 max-w-2xl mx-auto leading-relaxed">
            AI Portal gives your organization private, self-hosted access to frontier LLMs — with
            knowledge bases, persistent memory, and full data control.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href={`${getAppUrl()}/register`}
              className="rounded-xl bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors"
            >
              Start for free
            </a>
            <Link
              to="/features"
              className="rounded-xl border border-gray-200 bg-white px-8 py-3.5 text-base font-semibold text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800 transition-colors"
            >
              See features →
            </Link>
          </div>
        </div>
      </section>

      {/* Features grid */}
      <section className="py-24 bg-gray-50 dark:bg-gray-900/50">
        <div className="mx-auto max-w-6xl px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
              Everything your team needs
            </h2>
            <p className="mt-4 text-lg text-gray-600 dark:text-gray-400">
              Built for engineers and teams who want AI capabilities without giving up data control.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="rounded-2xl border border-gray-100 bg-white p-8 shadow-sm dark:border-gray-800 dark:bg-gray-900"
              >
                <div className="text-3xl mb-4">{f.icon}</div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  {f.title}
                </h3>
                <p className="text-gray-600 dark:text-gray-400 text-sm leading-relaxed">
                  {f.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
            Ready to get started?
          </h2>
          <p className="mt-4 text-lg text-gray-600 dark:text-gray-400">
            Sign up for free and have your team running in minutes. No credit card required.
          </p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href={`${getAppUrl()}/register`}
              className="rounded-xl bg-indigo-600 px-8 py-3.5 text-base font-semibold text-white hover:bg-indigo-700 transition-colors"
            >
              Create your workspace
            </a>
            <Link
              to="/pricing"
              className="text-base font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors"
            >
              View pricing →
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
