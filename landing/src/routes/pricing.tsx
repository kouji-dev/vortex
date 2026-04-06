import { createFileRoute } from '@tanstack/react-router'
import { getAppUrl } from '~/lib/app-url'

export const Route = createFileRoute('/pricing')({
  component: PricingPage,
})

const registerHref = `${getAppUrl()}/register`

const PLANS = [
  {
    name: 'Personal',
    price: 'Free',
    period: '',
    description: 'For individuals exploring AI Portal.',
    cta: 'Get started',
    ctaHref: registerHref,
    highlighted: false,
    features: [
      '1 workspace',
      'Unlimited conversations',
      '3 knowledge bases',
      '100 MB document storage',
      'Email + password auth',
      'Community support',
    ],
  },
  {
    name: 'Team',
    price: '$29',
    period: '/month',
    description: 'For small teams that need shared knowledge and assistants.',
    cta: 'Start free trial',
    ctaHref: registerHref,
    highlighted: true,
    features: [
      'Up to 10 members',
      'Unlimited conversations',
      'Unlimited knowledge bases',
      '10 GB document storage',
      'Shared assistants',
      'Org management',
      'Priority support',
    ],
  },
  {
    name: 'Self-hosted',
    price: 'Free',
    period: '',
    description: 'Deploy on your own infrastructure. Full control.',
    cta: 'Deploy on Render',
    ctaHref: 'https://render.com/deploy',
    highlighted: false,
    features: [
      'Unlimited members',
      'Unlimited storage',
      'Your own database',
      'Your own model keys',
      'Setup wizard included',
      'Open source',
    ],
  },
]

function PricingPage() {
  return (
    <div className="py-16">
      <div className="mx-auto max-w-5xl px-6">
        <div className="text-center mb-16">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white">Pricing</h1>
          <p className="mt-4 text-xl text-gray-600 dark:text-gray-400">
            Simple, transparent pricing. Start free, scale when you need to.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-2xl p-8 flex flex-col ${
                plan.highlighted
                  ? 'bg-indigo-600 text-white shadow-xl ring-2 ring-indigo-500 ring-offset-2 dark:ring-offset-gray-950'
                  : 'border border-gray-100 bg-white dark:border-gray-800 dark:bg-gray-900'
              }`}
            >
              <div className="mb-6">
                <h2
                  className={`text-lg font-semibold mb-1 ${
                    plan.highlighted ? 'text-indigo-100' : 'text-gray-900 dark:text-white'
                  }`}
                >
                  {plan.name}
                </h2>
                <div className="flex items-end gap-1 mb-2">
                  <span
                    className={`text-4xl font-bold ${
                      plan.highlighted ? 'text-white' : 'text-gray-900 dark:text-white'
                    }`}
                  >
                    {plan.price}
                  </span>
                  {plan.period && (
                    <span
                      className={`text-sm mb-1 ${
                        plan.highlighted ? 'text-indigo-200' : 'text-gray-500 dark:text-gray-400'
                      }`}
                    >
                      {plan.period}
                    </span>
                  )}
                </div>
                <p
                  className={`text-sm ${
                    plan.highlighted ? 'text-indigo-200' : 'text-gray-600 dark:text-gray-400'
                  }`}
                >
                  {plan.description}
                </p>
              </div>

              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map((f) => (
                  <li
                    key={f}
                    className={`flex items-start gap-2 text-sm ${
                      plan.highlighted ? 'text-indigo-100' : 'text-gray-600 dark:text-gray-400'
                    }`}
                  >
                    <span
                      className={`mt-0.5 font-bold ${
                        plan.highlighted ? 'text-indigo-200' : 'text-indigo-500'
                      }`}
                    >
                      ✓
                    </span>
                    {f}
                  </li>
                ))}
              </ul>

              <a
                href={plan.ctaHref}
                className={`block rounded-xl px-6 py-3 text-center text-sm font-semibold transition-colors ${
                  plan.highlighted
                    ? 'bg-white text-indigo-600 hover:bg-indigo-50'
                    : 'bg-indigo-600 text-white hover:bg-indigo-700'
                }`}
              >
                {plan.cta}
              </a>
            </div>
          ))}
        </div>

        <p className="mt-12 text-center text-sm text-gray-500 dark:text-gray-400">
          Prices shown are placeholders. Contact us for enterprise pricing.
        </p>
      </div>
    </div>
  )
}
