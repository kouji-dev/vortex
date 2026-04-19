import { Link } from '@tanstack/react-router'

type FeatureCardProps = {
  title: string
  description: string
  to: '/chat/conversations' | '/knowledge-bases' | '/memories'
}

export function FeatureCard({ title, description, to }: FeatureCardProps) {
  return (
    <Link
      to={to}
      className="group block rounded-xl border border-line bg-panel p-5 shadow-sm transition hover:border-line-2 hover:shadow"
    >
      <h2 className="text-lg font-semibold text-ink group-hover:text-accent">
        {title}
      </h2>
      <p className="mt-2 text-sm text-ink-3">{description}</p>
      <span className="mt-3 inline-block text-sm font-medium text-accent">
        Open →
      </span>
    </Link>
  )
}
