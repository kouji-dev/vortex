import { Link } from '@tanstack/react-router'
import { ChevronsLeft, ChevronsRight, LayoutDashboard, Library, MessageSquare } from 'lucide-react'

const linkBase =
  'flex items-center gap-3 rounded-md text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800'
const linkExpanded = 'px-3 py-2'
const linkCompact = 'justify-center px-2 py-2.5'
const activeClass =
  'bg-neutral-200 font-medium dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-800'

type AppSidebarProps = {
  compact: boolean
  onToggleCompact: () => void
}

export function AppSidebar({ compact, onToggleCompact }: AppSidebarProps) {
  return (
    <aside
      className={`flex h-full min-h-0 shrink-0 flex-col overflow-hidden border-r border-neutral-200 bg-neutral-50 transition-[width] duration-200 ease-out dark:border-neutral-800 dark:bg-neutral-950 ${
        compact ? 'w-14' : 'w-56'
      }`}
      aria-label="Main navigation"
    >
      <div
        className={`flex items-center border-b border-neutral-200 dark:border-neutral-800 ${
          compact ? 'justify-center py-2' : 'justify-end gap-2 px-3 py-2'
        }`}
      >
        {!compact && (
          <div className="min-w-0 flex-1 pr-1">
            <Link
              to="/"
              className="block truncate text-lg font-semibold tracking-tight text-neutral-900 dark:text-neutral-100"
            >
              AI Portal
            </Link>
            <p className="truncate text-xs text-neutral-500">Signed-in workspace</p>
          </div>
        )}
        <button
          type="button"
          onClick={onToggleCompact}
          className="rounded-md p-2 text-neutral-600 hover:bg-neutral-200 dark:text-neutral-400 dark:hover:bg-neutral-800"
          title={compact ? 'Expand sidebar' : 'Compact sidebar'}
          aria-label={compact ? 'Expand sidebar' : 'Compact sidebar'}
          aria-expanded={!compact}
        >
          {compact ? (
            <ChevronsRight className="size-5 shrink-0" aria-hidden />
          ) : (
            <ChevronsLeft className="size-5 shrink-0" aria-hidden />
          )}
        </button>
      </div>

      <nav
        className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overscroll-contain p-2"
        aria-busy={false}
      >
        <Link
          to="/"
          className={`${linkBase} ${compact ? linkCompact : linkExpanded}`}
          activeProps={{ className: `${linkBase} ${compact ? linkCompact : linkExpanded} ${activeClass}` }}
          activeOptions={{ exact: true }}
          title="Dashboard"
        >
          <LayoutDashboard className="size-5 shrink-0 text-neutral-600 dark:text-neutral-400" aria-hidden />
          {!compact && <span>Dashboard</span>}
          {compact && <span className="sr-only">Dashboard</span>}
        </Link>
        <Link
          to="/chat/conversations"
          className={`${linkBase} ${compact ? linkCompact : linkExpanded}`}
          activeOptions={{ exact: false }}
          activeProps={{ className: `${linkBase} ${compact ? linkCompact : linkExpanded} ${activeClass}` }}
          title="Chat"
        >
          <MessageSquare className="size-5 shrink-0 text-neutral-600 dark:text-neutral-400" aria-hidden />
          {!compact && <span>Chat</span>}
          {compact && <span className="sr-only">Chat</span>}
        </Link>
        <Link
          to="/knowledge-bases"
          className={`${linkBase} ${compact ? linkCompact : linkExpanded}`}
          activeOptions={{ exact: false }}
          activeProps={{ className: `${linkBase} ${compact ? linkCompact : linkExpanded} ${activeClass}` }}
          title="Knowledge bases"
        >
          <Library className="size-5 shrink-0 text-neutral-600 dark:text-neutral-400" aria-hidden />
          {!compact && <span>Knowledge bases</span>}
          {compact && <span className="sr-only">Knowledge bases</span>}
        </Link>
      </nav>
    </aside>
  )
}
