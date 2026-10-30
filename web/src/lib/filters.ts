import { addDays, format, parseISO, startOfMonth, startOfWeek } from 'date-fns'
import { useCallback, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import type { FilterParams } from './api'
import { useMeta } from './queries'

export const iso = (d: Date) => format(d, 'yyyy-MM-dd')

export type Preset = { key: string; label: string; range: (today: Date) => [Date, Date] }

export const PRESETS: Preset[] = [
  { key: 'today', label: 'Today', range: (t) => [t, t] },
  { key: 'yesterday', label: 'Yesterday', range: (t) => [addDays(t, -1), addDays(t, -1)] },
  { key: '7d', label: 'Last 7 days', range: (t) => [addDays(t, -6), t] },
  { key: 'week', label: 'This week', range: (t) => [startOfWeek(t, { weekStartsOn: 1 }), t] },
  { key: '30d', label: 'Last 30 days', range: (t) => [addDays(t, -29), t] },
  { key: 'month', label: 'This month', range: (t) => [startOfMonth(t), t] },
]

/** Dashboard filters live in the URL so views can be bookmarked and shared. */
export function useFilters(machineOverride?: number) {
  const [params, setParams] = useSearchParams()
  const { data: meta } = useMeta()
  // Plant production date comes from the API (night shift belongs to its start date).
  const [browserToday] = useState(() => iso(new Date()))
  const today = meta?.today ?? browserToday

  const filters: FilterParams = useMemo(() => {
    const from = params.get('from') ?? today
    const to = params.get('to') ?? from
    const machine = machineOverride
      ? [machineOverride]
      : params.getAll('machine').map(Number).filter(Boolean)
    const product = params.get('product')
    return {
      from,
      to: to < from ? from : to,
      shift: params.get('shift') ?? undefined,
      machine: machine.length ? machine : undefined,
      product: product ? Number(product) : undefined,
    }
  }, [params, today, machineOverride])

  const update = useCallback(
    (patch: Partial<FilterParams>) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch)) {
            next.delete(k)
            if (v === undefined || v === null || v === '') continue
            for (const item of Array.isArray(v) ? v : [v]) next.append(k, String(item))
          }
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )

  const includesToday = filters.to >= today
  const todayDate = parseISO(today)
  return { filters, update, today, todayDate, includesToday }
}
