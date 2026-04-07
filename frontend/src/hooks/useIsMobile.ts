import * as React from 'react'

const MOBILE_BREAKPOINT = 768

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = React.useState(
    () => typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT,
  )

  React.useEffect(() => {
    const check = () => {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT
      setIsMobile(mobile)
      document.documentElement.classList.toggle('compact', mobile)
    }
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  return isMobile
}
