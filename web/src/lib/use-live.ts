import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { MachineStatus, Weighing } from './api'

export type LiveListener = (rows: Weighing[]) => void

export type LiveState = {
  connected: boolean
  status: Record<number, MachineStatus>
  subscribe: (fn: LiveListener) => () => void
}

export const LiveContext = createContext<LiveState | null>(null)

export function useLive() {
  const ctx = useContext(LiveContext)
  if (!ctx) throw new Error('useLive must be used inside <LiveProvider>')
  return ctx
}

/** Rolling buffer of the latest weighings for one machine: API seed + rows pushed over SSE. */
export function useLiveWeighings(machineId: number, seed: Weighing[] | undefined, max = 240) {
  const { subscribe } = useLive()
  const [pushed, setPushed] = useState<Weighing[]>([])

  useEffect(
    () =>
      subscribe((incoming) => {
        const mine = incoming.filter((w) => w.machine_id === machineId)
        if (mine.length) setPushed((prev) => [...prev, ...mine].slice(-max))
      }),
    [subscribe, machineId, max],
  )

  return useMemo(() => {
    const base = seed ?? []
    const lastTs = base.at(-1)?.ts
    const fresh = lastTs ? pushed.filter((w) => w.ts > lastTs) : pushed
    return [...base, ...fresh].slice(-max)
  }, [seed, pushed, max])
}
