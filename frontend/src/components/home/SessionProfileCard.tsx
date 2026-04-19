import type { UseQueryResult } from '@tanstack/react-query'
import { PrismLogo } from '~/components/brand'

import type { MeResponse } from '~/lib/me-types'

type SessionProfileCardProps = {
  me: UseQueryResult<MeResponse>
}

export function SessionProfileCard({ me }: SessionProfileCardProps) {
  return (
    <div className="rounded-xl border border-line bg-bg-2 p-5">
      <h2 className="text-lg font-semibold text-ink">Your session</h2>
      <p className="mt-1 text-xs text-ink-3">
        <code className="rounded bg-bg px-1">GET /api/me</code>
      </p>
      {me.isPending && <PrismLogo state="loading" size={16} className="mt-3" />}
      {me.isError && (
        <p className="mt-3 text-sm text-warn">
          {(me.error as Error).message}
        </p>
      )}
      {me.isSuccess && (
        <div className="mt-3 space-y-2 text-sm text-ink-2">
          <p>
            <strong>{me.data.email}</strong>
            <span className="text-ink-3"> (id {me.data.id})</span>
            {me.data.roles.length > 0 && (
              <span className="text-ink-3">
                {' '}
                — roles: {me.data.roles.join(', ')}
              </span>
            )}
          </p>
          {(me.data.display_name ||
            me.data.given_name ||
            me.data.family_name ||
            me.data.preferred_username) && (
            <ul className="list-inside list-disc text-ink-3">
              {me.data.display_name && (
                <li>
                  <span className="font-medium text-ink-2">Name</span>:{' '}
                  {me.data.display_name}
                </li>
              )}
              {(me.data.given_name || me.data.family_name) && (
                <li>
                  <span className="font-medium text-ink-2">
                    Given / family
                  </span>
                  : {[me.data.given_name, me.data.family_name].filter(Boolean).join(' ')}
                </li>
              )}
              {me.data.preferred_username && (
                <li>
                  <span className="font-medium text-ink-2">
                    Preferred username
                  </span>
                  : {me.data.preferred_username}
                </li>
              )}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
