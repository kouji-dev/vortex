/**
 * ModuleShell — chat-style two-pane layout shared by Gateway / RAG / Workers /
 * Admin. Left: a white section-nav panel styled like the chat thread list.
 * Right: a white ribbon header (showing the active section) over a scrollable
 * body that renders the route's <Outlet />.
 *
 * Ribbon titles are plain <div>s (not headings) so they never collide with a
 * sub-page's own headings in E2E `getByRole('heading')` queries.
 */
import { Link, useRouterState } from '@tanstack/react-router'
import * as React from 'react'

export type ModuleNavItem = {
  to: string
  label: string
  testId?: string
  badge?: string
  disabled?: boolean
  /** Custom active predicate; defaults to `pathname.startsWith(to)`. */
  isActive?: (pathname: string) => boolean
}

export type ModuleNavGroup = {
  label?: string
  items: readonly ModuleNavItem[]
}

export type ModuleShellProps = {
  /** Shown at the top of the left nav panel. */
  moduleName: string
  /** Optional one-line subtitle under the module name + default ribbon subtitle. */
  moduleSub?: string
  groups: readonly ModuleNavGroup[]
  /** Override the ribbon title (defaults to the active section label). */
  ribbonTitle?: string
  /** Override the ribbon subtitle (defaults to moduleSub). */
  ribbonSub?: string
  /** Actions rendered on the right side of the ribbon. */
  ribbonActions?: React.ReactNode
  testId?: string
  children: React.ReactNode
}

export function ModuleShell({
  moduleName,
  moduleSub,
  groups,
  ribbonTitle,
  ribbonSub,
  ribbonActions,
  testId,
  children,
}: ModuleShellProps) {
  const pathname = useRouterState({ select: (s) => s.location.pathname })

  const itemActive = React.useCallback(
    (it: ModuleNavItem) =>
      !it.disabled && (it.isActive ? it.isActive(pathname) : pathname.startsWith(it.to)),
    [pathname],
  )

  // Most specific (last-declared) active item wins — e.g. RAG's per-KB tab
  // outranks the global "Knowledge bases" entry.
  const activeLabel = React.useMemo(() => {
    let label: string | undefined
    for (const g of groups) {
      for (const it of g.items) {
        if (itemActive(it)) label = it.label
      }
    }
    return label
  }, [groups, itemActive])

  return (
    <div className="module-shell" data-testid={testId}>
      <nav className="module-nav" aria-label={`${moduleName} sections`}>
        <div className="module-nav-head">
          <div className="module-nav-title">{moduleName}</div>
          {moduleSub && <div className="module-nav-sub">{moduleSub}</div>}
        </div>
        <div className="module-nav-scroll">
          {groups.map((g, gi) => (
            <React.Fragment key={g.label ?? `g${gi}`}>
              {g.label && <div className="module-nav-group">{g.label}</div>}
              {g.items.map((it) => {
                const active = itemActive(it)
                const cls = `module-nav-item${active ? ' active' : ''}${
                  it.disabled ? ' disabled' : ''
                }`
                const inner = (
                  <>
                    {it.label}
                    {it.badge && <span className="module-nav-badge">{it.badge}</span>}
                  </>
                )
                if (it.disabled) {
                  return (
                    <span key={it.to} className={cls} data-testid={it.testId} aria-disabled="true">
                      {inner}
                    </span>
                  )
                }
                return (
                  <Link key={it.to} to={it.to} className={cls} data-testid={it.testId}>
                    {inner}
                  </Link>
                )
              })}
            </React.Fragment>
          ))}
        </div>
      </nav>

      <section className="module-pane">
        <header className="module-ribbon">
          <div className="module-ribbon-titles">
            <div className="module-ribbon-title">{ribbonTitle ?? activeLabel ?? moduleName}</div>
            {(ribbonSub ?? moduleSub) && (
              <div className="module-ribbon-sub">{ribbonSub ?? moduleSub}</div>
            )}
          </div>
          {ribbonActions && <div className="module-ribbon-actions">{ribbonActions}</div>}
        </header>
        <div className="module-body">{children}</div>
      </section>
    </div>
  )
}
