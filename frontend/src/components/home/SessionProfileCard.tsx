import type { UseQueryResult } from '@tanstack/react-query'

import type { MeResponse } from '~/lib/me-types'

type SessionProfileCardProps = {
  me: UseQueryResult<MeResponse>
}

export function SessionProfileCard({ me }: SessionProfileCardProps) {
  return (
    <div className="rounded-xl border border-neutral-200 bg-neutral-50/80 p-5 dark:border-neutral-800 dark:bg-neutral-900/50">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Your session</h2>
      <p className="mt-1 text-xs text-neutral-500">
        <code className="rounded bg-neutral-200/80 px-1 dark:bg-neutral-800">GET /api/me</code>
      </p>
      {me.isPending && <p className="mt-3 text-sm text-neutral-500">Loading profile…</p>}
      {me.isError && (
        <p className="mt-3 text-sm text-amber-700 dark:text-amber-400">
          {(me.error as Error).message}
        </p>
      )}
      {me.isSuccess && (
        <div className="mt-3 space-y-2 text-sm text-neutral-800 dark:text-neutral-200">
          <p>
            <strong>{me.data.email}</strong>
            <span className="text-neutral-500"> (id {me.data.id})</span>
            {me.data.roles.length > 0 && (
              <span className="text-neutral-600 dark:text-neutral-400">
                {' '}
                — roles: {me.data.roles.join(', ')}
              </span>
            )}
          </p>
          {(me.data.display_name ||
            me.data.given_name ||
            me.data.family_name ||
            me.data.preferred_username) && (
            <ul className="list-inside list-disc text-neutral-600 dark:text-neutral-400">
              {me.data.display_name && (
                <li>
                  <span className="font-medium text-neutral-700 dark:text-neutral-300">Name</span>:{' '}
                  {me.data.display_name}
                </li>
              )}
              {(me.data.given_name || me.data.family_name) && (
                <li>
                  <span className="font-medium text-neutral-700 dark:text-neutral-300">
                    Given / family
                  </span>
                  : {[me.data.given_name, me.data.family_name].filter(Boolean).join(' ')}
                </li>
              )}
              {me.data.preferred_username && (
                <li>
                  <span className="font-medium text-neutral-700 dark:text-neutral-300">
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
