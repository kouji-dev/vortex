import { Link } from '@tanstack/react-router'
import { Brain, ChevronsLeft, ChevronsRight, LayoutDashboard, Library, MessageSquare } from 'lucide-react'
import { PrismLogo, VortexWordmark } from '~/components/brand'

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
      className={`hidden md:flex h-full min-h-0 shrink-0 flex-col overflow-hidden border-r border-neutral-200 bg-neutral-50 transition-[width] duration-200 ease-out dark:border-neutral-800 dark:bg-neutral-950 ${
        compact ? 'w-14' : 'w-56'
      }`}
      aria-label="Main navigation"
    >
      <div
        className={`flex border-b border-neutral-200 dark:border-neutral-800 ${
          compact
            ? 'flex-col items-center gap-1 py-2'
            : 'flex-row items-center justify-end gap-2 px-3 py-2'
        }`}
      >
        {!compact && (
          <Link to="/" className="flex min-w-0 flex-1 items-center gap-2 pr-1">
            <PrismLogo state="mono-white" size={22} />
            <VortexWordmark variant="white" size={17} />
          </Link>
        )}
        {compact && (
          <Link to="/" aria-label="Vortex home">
            <PrismLogo state="mono-white" size={22} />
          </Link>
        )}
        <button
          type="button"
          onClick={onToggleCompact}
          className="rounded-md p-1.5 text-neutral-600 hover:bg-neutral-200 dark:text-neutral-400 dark:hover:bg-neutral-800"
          title={compact ? 'Expand sidebar' : 'Compact sidebar'}
          aria-label={compact ? 'Expand sidebar' : 'Compact sidebar'}
          aria-expanded={!compact}
        >
          {compact ? (
            <ChevronsRight className="size-4 shrink-0" aria-hidden />
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
        <Link
          to="/memories"
          className={`${linkBase} ${compact ? linkCompact : linkExpanded}`}
          activeOptions={{ exact: false }}
          activeProps={{ className: `${linkBase} ${compact ? linkCompact : linkExpanded} ${activeClass}` }}
          title="Memories"
        >
          <Brain className="size-5 shrink-0 text-neutral-600 dark:text-neutral-400" aria-hidden />
          {!compact && <span>Memories</span>}
          {compact && <span className="sr-only">Memories</span>}
        </Link>
      </nav>
    </aside>
  )
}
