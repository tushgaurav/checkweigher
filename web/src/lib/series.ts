import type { Product } from './api'

// Series colours / legends shared by the charts and their panel footers.

export type LegendItem = { label: string; color: string; shape?: 'dot' | 'line' | 'dash' | 'square' }

export type LimitSet = Pick<Product, 'target_g' | 'hi_g' | 'lo_g' | 'hihi_g' | 'lolo_g'>

export const LIMITS: { key: keyof LimitSet; label: string; color: string; dash: string; name: string }[] = [
  { key: 'lolo_g', label: 'LL', name: 'LoLo', color: 'var(--under)', dash: '2 4' },
  { key: 'lo_g', label: 'LO', name: 'Lo', color: 'var(--under)', dash: '5 3' },
  { key: 'target_g', label: 'T', name: 'Target', color: 'var(--signal)', dash: '' },
  { key: 'hi_g', label: 'HI', name: 'Hi', color: 'var(--over)', dash: '5 3' },
  { key: 'hihi_g', label: 'HH', name: 'HiHi', color: 'var(--over)', dash: '2 4' },
]

export const HISTOGRAM_LEGEND: LegendItem[] = [
  { label: 'Below Lo', color: 'var(--under)' },
  { label: 'Within limits', color: 'var(--ok)' },
  { label: 'Above Hi', color: 'var(--over)' },
]

export const WEIGHT_LEGEND: LegendItem[] = [
  { label: 'Mean weight', color: 'var(--chart-1)', shape: 'line' },
  { label: 'Min – max', color: 'color-mix(in oklch, var(--chart-1) 25%, transparent)' },
  { label: 'Target', color: 'var(--signal)', shape: 'dash' },
]

// EGA is typically well under 1 % while reject rates can be tens of %: EGA gets its own axis.
export const RATE_SERIES = [
  { key: 'ega_pct', label: 'EGA %', color: 'var(--signal)', axis: 'ega' },
  { key: 'overweight_pct', label: 'Overweight %', color: 'var(--over)', axis: 'rate' },
  { key: 'underweight_pct', label: 'Underweight %', color: 'var(--under)', axis: 'rate' },
  { key: 'feeding_error_pct', label: 'Feeding error %', color: 'var(--feed)', axis: 'rate' },
] as const

export const RATES_LEGEND: LegendItem[] = RATE_SERIES.map((s) => ({
  label: s.axis === 'ega' ? `${s.label} (right axis)` : s.label,
  color: s.color,
  shape: 'line',
}))

export const THROUGHPUT_LEGEND: LegendItem[] = [
  { label: 'Passed', color: 'var(--ok)' },
  { label: 'Rejected', color: 'var(--reject)' },
]

export const JUDGEMENT_LEGEND: LegendItem[] = [
  { label: 'OK', color: 'var(--ok)', shape: 'dot' },
  { label: 'Over', color: 'var(--over)', shape: 'dot' },
  { label: 'Under', color: 'var(--under)', shape: 'dot' },
  { label: 'Feeding', color: 'var(--feed)', shape: 'dot' },
  { label: 'Metal / ext.', color: 'var(--reject)', shape: 'dot' },
]
