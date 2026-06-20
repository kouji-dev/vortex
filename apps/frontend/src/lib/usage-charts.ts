/**
 * Pure helpers for the Usage page SVG charts. Kept separate so they can
 * be unit tested without React. No Recharts dep — minimal hand-rolled charts.
 */
import type { UsageBucket, UsageTimeseriesPoint } from './admin-types'

export interface ScaledBar {
  label: string
  value: number
  /** width in px, 0..maxWidth */
  width: number
  pct: number // 0..1
}

export interface ScaledLinePoint {
  x: number // px
  y: number // px (0 at top)
  ts: string
  value: number
}

/**
 * Scale a set of bucket values to a horizontal bar chart of width `maxWidth`.
 * Selector picks which numeric metric to scale.
 */
export function scaleBars(
  buckets: UsageBucket[],
  selector: (b: UsageBucket) => number,
  maxWidth: number,
): ScaledBar[] {
  if (!buckets || buckets.length === 0) return []
  const values = buckets.map(selector)
  const max = Math.max(...values, 1) // never divide by zero
  return buckets.map((b, i) => {
    const value = values[i]
    const pct = value / max
    return {
      label: b.dim_label,
      value,
      width: Math.round(pct * maxWidth),
      pct,
    }
  })
}

/**
 * Scale a timeseries to a line/area chart, fitting inside (width, height) box.
 * Returns points in pixel space (y-axis inverted: 0 = top).
 */
export function scaleTimeseries(
  points: UsageTimeseriesPoint[],
  selector: (p: UsageTimeseriesPoint) => number,
  width: number,
  height: number,
): ScaledLinePoint[] {
  if (!points || points.length === 0) return []
  const values = points.map(selector)
  const max = Math.max(...values, 1)
  const n = points.length
  return points.map((p, i) => {
    const value = values[i]
    const x = n === 1 ? width / 2 : (i / (n - 1)) * width
    const y = height - (value / max) * height
    return { x, y, ts: p.ts, value }
  })
}

/**
 * SVG path "M x0,y0 L x1,y1 …" for a line chart from scaled points.
 */
export function buildLinePath(points: ScaledLinePoint[]): string {
  if (points.length === 0) return ''
  return points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)},${p.y.toFixed(2)}`)
    .join(' ')
}

/**
 * Format cents as dollars with sensible precision.
 */
export function formatCost(cents: number): string {
  if (cents == null || Number.isNaN(cents)) return '—'
  const dollars = cents / 100
  if (dollars >= 100) return `$${dollars.toFixed(0)}`
  if (dollars >= 1) return `$${dollars.toFixed(2)}`
  if (dollars >= 0.01) return `$${dollars.toFixed(4)}`
  return `$${dollars.toFixed(6)}`
}

/**
 * Format token counts with k/M suffix.
 */
export function formatTokens(n: number): string {
  if (n == null || Number.isNaN(n)) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}
