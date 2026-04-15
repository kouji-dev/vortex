// landing/src/hooks/useScrollReveal.ts
import { useEffect, useRef } from 'react'

export function useScrollReveal<T extends HTMLElement>(
  options?: IntersectionObserverInit
) {
  const ref = useRef<T>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('visible')
          obs.unobserve(el)
        }
      },
        { threshold: 0.1, rootMargin: '0px 0px -40px 0px', ...options }
    )
    obs.observe(el)
    return () => obs.disconnect()
  // options intentionally excluded: all callers pass stable objects or no args.
  // If a caller passes an inline object literal, the initial options will be used.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return ref
}
