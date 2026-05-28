/**
 * Audit filter normalization. UI inputs (local date strings, possibly empty)
 * → API-ready filter struct with ISO datetimes.
 */
import type { AuditFilter } from './admin-types'

export interface AuditFilterUiInputs {
  action: string
  actor: string
  resourceType: string
  resourceId: string
  /** "yyyy-MM-dd" or empty */
  fromDate: string
  /** "yyyy-MM-dd" or empty */
  toDate: string
}

export function normalizeAuditFilter(inputs: AuditFilterUiInputs): AuditFilter {
  const out: AuditFilter = { limit: 100 }
  const trim = (v: string) => v.trim()
  if (trim(inputs.action)) out.action = trim(inputs.action)
  if (trim(inputs.actor)) out.actor = trim(inputs.actor)
  if (trim(inputs.resourceType)) out.resource_type = trim(inputs.resourceType)
  if (trim(inputs.resourceId)) out.resource_id = trim(inputs.resourceId)
  if (inputs.fromDate) out.from = dateOnlyToIsoStart(inputs.fromDate)
  if (inputs.toDate) out.to = dateOnlyToIsoEnd(inputs.toDate)
  return out
}

function dateOnlyToIsoStart(d: string): string {
  // start of day UTC
  return new Date(`${d}T00:00:00.000Z`).toISOString()
}

function dateOnlyToIsoEnd(d: string): string {
  // end of day UTC (next day boundary minus 1ms)
  return new Date(`${d}T23:59:59.999Z`).toISOString()
}

/**
 * Returns true if the from/to range is logically valid (from <= to).
 * Empty fields are always valid (no constraint).
 */
export function isRangeValid(fromDate: string, toDate: string): boolean {
  if (!fromDate || !toDate) return true
  return fromDate <= toDate
}
