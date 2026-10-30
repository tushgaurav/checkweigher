const DASH = '—'
const locale = 'en-IN' // lakh/crore grouping for Indian plants

const intFmt = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 })
const cache = new Map<number, Intl.NumberFormat>()
function fixed(digits: number) {
  let f = cache.get(digits)
  if (!f) {
    f = new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits })
    cache.set(digits, f)
  }
  return f
}

type N = number | null | undefined

export const fmtInt = (v: N) => (v == null ? DASH : intFmt.format(v))
export const fmtNum = (v: N, digits = 1) => (v == null ? DASH : fixed(digits).format(v))
export const fmtPct = (v: N, digits = 2) => (v == null ? DASH : `${fixed(digits).format(v)}%`)
export const fmtG = (v: N, digits = 1) => (v == null ? DASH : `${fixed(digits).format(v)} g`)
export const fmtKg = (v: N, digits = 1) => (v == null ? DASH : `${fixed(digits).format(v)} kg`)
export const fmtSigned = (v: N, digits = 1) =>
  v == null ? DASH : `${v > 0 ? '+' : v < 0 ? '−' : '±'}${fixed(digits).format(Math.abs(v))}`

export function fmtTime(iso: string | null | undefined, tz?: string) {
  if (!iso) return DASH
  return new Date(iso).toLocaleTimeString(locale, { hour12: false, timeZone: tz })
}

export function fmtDateTime(iso: string | null | undefined, tz?: string) {
  if (!iso) return DASH
  return new Date(iso).toLocaleString(locale, {
    hour12: false,
    timeZone: tz,
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function fmtAgo(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return DASH
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export const productLabel = (p: { group_no: number; product_no: number } | null | undefined) =>
  p ? `G${p.group_no}·P${p.product_no}` : DASH
