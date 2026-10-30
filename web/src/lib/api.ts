import type { components } from './api-types'

// Regenerate with `npm run gen:api` while the API is running.
type Schemas = components['schemas']
export type Meta = Schemas['Meta']
export type Summary = Schemas['Summary']
export type KPIs = Schemas['KPIs']
export type MachineSummary = Schemas['MachineSummary']
export type Product = Schemas['Product']
export type Trend = Schemas['Trend']
export type TrendPoint = Schemas['TrendPoint']
export type Histogram = Schemas['Histogram']
export type Weighing = Schemas['Weighing']
export type Weighings = Schemas['Weighings']
export type Event = Schemas['Event']
export type MachineStatus = Schemas['MachineStatus']
export type LastWeight = Schemas['LastWeight']
export type Completeness = Schemas['Completeness']

export type FilterParams = {
  from: string
  to: string
  shift?: string
  machine?: number[]
  product?: number
}

type Query = Record<string, string | number | (string | number)[] | undefined | null>

export function toQuery(q: Query): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === '') continue
    for (const item of Array.isArray(v) ? v : [v]) p.append(k, String(item))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export function filterQuery(f: FilterParams, extra: Query = {}): string {
  return toQuery({
    date_from: f.from,
    date_to: f.to,
    shift: f.shift,
    machine_id: f.machine,
    product_id: f.product,
    ...extra,
  })
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const exportUrl = (f: FilterParams) => `/api/export.xlsx${filterQuery(f)}`
