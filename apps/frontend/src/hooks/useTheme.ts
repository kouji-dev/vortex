import { useCallback, useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'vx.theme'
const THEME_EVENT = 'vx:theme-change'

function isTheme(v: unknown): v is Theme {
  return v === 'light' || v === 'dark'
}

function systemPreference(): Theme {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** Reads the current theme, preferring localStorage, then the `<html data-theme>`, then system. */
function readTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (isTheme(stored)) return stored
  } catch { /* private mode, quota, etc. — fall through */ }
  const attr = document.documentElement.getAttribute('data-theme')
  if (isTheme(attr)) return attr
  return systemPreference()
}

function writeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme)
  } catch { /* ignore */ }
  document.documentElement.setAttribute('data-theme', theme)
  window.dispatchEvent(new CustomEvent(THEME_EVENT))
}

function subscribe(onStoreChange: () => void): () => void {
  const onCustom = () => onStoreChange()
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) onStoreChange()
  }
  window.addEventListener(THEME_EVENT, onCustom)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(THEME_EVENT, onCustom)
    window.removeEventListener('storage', onStorage)
  }
}

/** Sync the `<html data-theme>` attribute once, on module load, from localStorage. */
export function bootstrapTheme(): void {
  if (typeof window === 'undefined') return
  const theme = readTheme()
  document.documentElement.setAttribute('data-theme', theme)
}

/**
 * Theme hook backed by localStorage. Uses `useSyncExternalStore` so multiple
 * consumers stay in sync and cross-tab changes propagate via the `storage` event.
 */
export function useTheme(): readonly [Theme, (next: Theme) => void, () => void] {
  const theme = useSyncExternalStore<Theme>(subscribe, readTheme, () => 'light')

  const setTheme = useCallback((next: Theme) => {
    writeTheme(next)
  }, [])

  const toggle = useCallback(() => {
    writeTheme(readTheme() === 'light' ? 'dark' : 'light')
  }, [])

  return [theme, setTheme, toggle] as const
}
