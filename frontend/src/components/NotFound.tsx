import { Link } from '@tanstack/react-router'

export function NotFound({ children }: { children?: any }) {
  return (
    <div className="space-y-2 p-2">
      <div className="text-ink-3">
        {children || <p>The page you are looking for does not exist.</p>}
      </div>
      <p className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => window.history.back()}
          className="btn btn-primary"
        >
          Go back
        </button>
        <Link
          to="/"
          className="btn"
        >
          Start Over
        </Link>
      </p>
    </div>
  )
}
