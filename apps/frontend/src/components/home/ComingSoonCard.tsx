type ComingSoonCardProps = {
  title: string
  description: string
}

export function ComingSoonCard({ title, description }: ComingSoonCardProps) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-bg-2 p-5">
      <h2 className="text-lg font-semibold text-ink-3">{title}</h2>
      <p className="mt-2 text-sm text-ink-3">{description}</p>
      <span className="mt-3 inline-block text-xs font-medium uppercase tracking-wide text-ink-4">
        Coming soon
      </span>
    </div>
  )
}
