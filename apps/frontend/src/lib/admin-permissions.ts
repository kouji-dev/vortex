/**
 * Client-side admin gate. UX hint only — server enforces with require_permission.
 * Owner or admin roles see the Admin section; anyone else gets the 403 panel.
 */
export function isAdminActor(roles: string[] | undefined | null): boolean {
  if (!roles) return false
  return roles.some((r) => r === 'owner' || r === 'admin')
}
