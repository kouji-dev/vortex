import * as React from 'react'

/** Matches Tailwind v4 default `dark:` (prefers-color-scheme). */
export function usePrefersColorSchemeDark(): boolean {
  const [dark, setDark] = React.useState(false)

  React.useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => setDark(mq.matches)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  return dark
}
