type ComingSoonCardProps = {
  title: string
  description: string
}

export function ComingSoonCard({ title, description }: ComingSoonCardProps) {
  return (
    <div className="rounded-xl border border-dashed border-neutral-300 bg-neutral-50/50 p-5 dark:border-neutral-700 dark:bg-neutral-900/30">
      <h2 className="text-lg font-semibold text-neutral-500 dark:text-neutral-400">{title}</h2>
      <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-500">{description}</p>
      <span className="mt-3 inline-block text-xs font-medium uppercase tracking-wide text-neutral-400">
        Coming soon
      </span>
    </div>
  )
}
