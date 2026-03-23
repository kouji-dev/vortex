import { Link } from '@tanstack/react-router'

type FeatureCardProps = {
  title: string
  description: string
  to: '/chat/conversations'
}

export function FeatureCard({ title, description, to }: FeatureCardProps) {
  return (
    <Link
      to={to}
      className="group block rounded-xl border border-neutral-200 bg-white p-5 shadow-sm transition hover:border-neutral-300 hover:shadow dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700"
    >
      <h2 className="text-lg font-semibold text-neutral-900 group-hover:text-blue-700 dark:text-neutral-100 dark:group-hover:text-blue-400">
        {title}
      </h2>
      <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">{description}</p>
      <span className="mt-3 inline-block text-sm font-medium text-blue-600 dark:text-blue-400">
        Open →
      </span>
    </Link>
  )
}
