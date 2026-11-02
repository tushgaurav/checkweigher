import { useSyncExternalStore, type RefObject } from 'react'

const subscribe = (fn: () => void) => {
  document.addEventListener('fullscreenchange', fn)
  return () => document.removeEventListener('fullscreenchange', fn)
}
const current = () => document.fullscreenElement

/** Fullscreen for one element (a panel) or, without a target, the whole page (kiosk displays). */
export function useFullscreen(target?: RefObject<HTMLElement | null>) {
  const el = useSyncExternalStore(subscribe, current)
  const active = el != null && (!target || el === target.current)
  const toggle = () => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void (target?.current ?? document.documentElement).requestFullscreen()
  }
  return { active, toggle, supported: document.fullscreenEnabled }
}
