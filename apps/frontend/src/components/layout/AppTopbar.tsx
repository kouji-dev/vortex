import { Link } from '@tanstack/react-router'
import { Moon, Search, Sun } from 'lucide-react'
import * as React from 'react'

import { useHealthQuery } from '~/hooks/useHealthQuery'
import { useMeQuery } from '~/hooks/useMeQuery'
import { useTheme } from '~/hooks/useTheme'

/** Returns up to 2 initials from a display name or email. */
function initials(me: { display_name?: string | null; email?: string }): string {
  const name = me.display_name?.trim()
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean)
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    return name.slice(0, 2).toUpperCase()
  }
  if (me.email) return me.email.slice(0, 2).toUpperCase()
  return '??'
}

function ThemeToggle() {
  const [theme, , toggle] = useTheme()

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle theme"
      className="topbar-chip"
      data-testid="topbar-theme-toggle"
    >
      {theme === 'light' ? <Moon size={12} aria-hidden /> : <Sun size={12} aria-hidden />}
    </button>
  )
}

export function AppTopbar() {
  const health = useHealthQuery()
  const me = useMeQuery()

  const isHealthy = health.data?.status === 'ok'
  const avatarLabel = me.data ? initials(me.data) : '…'

  return (
    <header className="topbar" data-testid="app-topbar">
      <Link to="/" className="brand" aria-label="Home">
        <span className="brand-mark" aria-hidden>VX</span>
        <span className="brand-name">Vortex</span>
        <span className="brand-env mono">
          {health.data?.deployment_mode ?? 'dev'}
        </span>
      </Link>

      <div className="topbar-search" role="search">
        <Search size={13} aria-hidden />
        <input
          type="text"
          placeholder="Search conversations, knowledge bases, memories…"
          aria-label="Search"
        />
        <kbd>⌘K</kbd>
      </div>

      <div className="topbar-right">
        <span className="topbar-chip" data-testid="topbar-health">
          <span
            className="dot"
            aria-hidden
            style={isHealthy ? undefined : { background: 'var(--err)' }}
          />
          {isHealthy ? 'Healthy' : 'Degraded'}
        </span>
        <span className="divider" aria-hidden />
        <ThemeToggle />
        {/* Avatar — wired to useMeQuery; TODO: link to account settings once route exists */}
        <div
          className="avatar"
          role="button"
          aria-label="Account"
          data-testid="topbar-avatar"
        >
          {avatarLabel}
        </div>
      </div>
    </header>
  )
}
