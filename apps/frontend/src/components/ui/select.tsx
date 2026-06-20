import * as React from 'react'

import { cn } from '~/lib/utils'

export type SelectProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'> & {
  /** Compact density for toolbars and table rows. Default `md` suits form rows. */
  size?: 'sm' | 'md'
  /** Hug-content width instead of the form-default full width (for inline toolbars). */
  inline?: boolean
}

/**
 * App-wide select. A native select styled with the Vortex `.select`
 * design-system class (themed border, focus ring, and chevron) so every dropdown
 * in the app looks identical. Native semantics are preserved, so `<option>`
 * children, `value`/`onChange`, `data-testid`, and Playwright `selectOption`
 * all keep working.
 *
 * @example
 * <Select value={period} onChange={(e) => setPeriod(e.target.value)} size="sm" inline>
 *   {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
 * </Select>
 */
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, size = 'md', inline, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      className={cn('select', size === 'sm' && 'select-sm', inline && 'select-inline', className)}
      {...props}
    >
      {children}
    </select>
  )
})
