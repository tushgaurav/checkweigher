import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

// index.html applies the stored choice before first paint; light is the default.
export const THEME_KEY = 'cw-theme'

const listeners = new Set<() => void>()
const read = (): Theme => (document.documentElement.classList.contains('dark') ? 'dark' : 'light')

export function setTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.add('theme-switching')
  root.classList.toggle('dark', theme === 'dark')
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    /* storage unavailable (private mode / kiosk): theme still applies for this session */
  }
  listeners.forEach((fn) => fn())
  // Re-enable transitions once the new colours have been painted.
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-switching')))
}

export function useTheme(): Theme {
  return useSyncExternalStore((fn) => {
    listeners.add(fn)
    return () => listeners.delete(fn)
  }, read)
}
