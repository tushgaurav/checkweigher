import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import type { MachineStatus, Weighing } from './api'
import { LiveContext, type LiveListener } from './use-live'

/** One EventSource for the whole app: machine status + newly stored weighings (~1 Hz). */
export function LiveProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState<Record<number, MachineStatus>>({})
  const listeners = useRef(new Set<LiveListener>())

  useEffect(() => {
    const es = new EventSource('/api/live')
    es.addEventListener('open', () => setConnected(true))
    es.addEventListener('error', () => setConnected(false))
    es.addEventListener('tick', (e) => {
      const payload = JSON.parse((e as MessageEvent).data) as { status: MachineStatus[]; weighings: Weighing[] }
      setConnected(true)
      setStatus(Object.fromEntries(payload.status.map((s) => [s.machine_id, s])))
      if (payload.weighings.length) listeners.current.forEach((fn) => fn(payload.weighings))
    })
    return () => es.close()
  }, [])

  const subscribe = useCallback((fn: LiveListener) => {
    listeners.current.add(fn)
    return () => {
      listeners.current.delete(fn)
    }
  }, [])

  return <LiveContext.Provider value={{ connected, status, subscribe }}>{children}</LiveContext.Provider>
}
