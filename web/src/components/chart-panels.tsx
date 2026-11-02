import { useState } from 'react'
import { HistogramChart, LiveWeightChart, RatesTrendChart, ThroughputChart, WeightTrendChart } from '@/components/charts'
import { FooterStats, Legend, Panel } from '@/components/panel'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { FilterParams, Histogram, KPIs, Product, TrendPoint, Weighing } from '@/lib/api'
import { fmtG, fmtInt, fmtNum, fmtPct, fmtSigned, productLabel } from '@/lib/format'
import { useTrend } from '@/lib/queries'
import {
  HISTOGRAM_LEGEND,
  JUDGEMENT_LEGEND,
  LIMITS,
  RATES_LEGEND,
  THROUGHPUT_LEGEND,
  WEIGHT_LEGEND,
} from '@/lib/series'

const INTERVALS = [
  { key: 'auto', label: 'Auto' },
  { key: '15m', label: '15m' },
  { key: '1h', label: '1h' },
  { key: 'shift', label: 'Shift' },
  { key: '1d', label: 'Day' },
]

const BUCKET_TEXT: Record<string, string> = {
  '15m': 'per 15 min',
  '1h': 'per hour',
  shift: 'per shift',
  '1d': 'per day',
}

const bucketText = (interval: string | undefined) => (interval ? (BUCKET_TEXT[interval] ?? interval) : '')
const fileTag = (f: FilterParams) => `${f.from}_${f.to}${f.shift ? `_${f.shift}` : ''}`

const trendRows = (points: TrendPoint[]) =>
  points.map((p) => ({
    bucket_start: p.t,
    label: p.label,
    judged: p.total,
    passed: p.passed,
    mean_g: p.mean_g,
    sd_g: p.sd_g,
    min_g: p.min_g,
    max_g: p.max_g,
    target_g: p.mean_target_g,
    ega_pct: p.ega_pct,
    overweight_pct: p.overweight_pct,
    underweight_pct: p.underweight_pct,
    feeding_error_pct: p.feeding_error_pct,
    rejected_pct: p.rejected_pct,
  }))

type TrendProps = {
  filters: FilterParams
  includesToday: boolean
  scope: string
  k: KPIs | undefined
  productCount?: number
}

export function TrendPanels({ filters, includesToday, scope, k, productCount = 1 }: TrendProps) {
  const [interval, setIntervalKey] = useState('auto')
  const { data } = useTrend(filters, interval, includesToday)
  const points = data?.points ?? []
  const subtitle = `${scope} · ${bucketText(data?.interval)}`
  const csv = { name: `trend_${fileTag(filters)}`, rows: () => trendRows(points) }
  const picker = (
    <ToggleGroup
      type="single"
      variant="outline"
      spacing={0}
      value={interval}
      onValueChange={(v) => v && setIntervalKey(v)}
      aria-label="Bucket size"
      className="mr-1"
    >
      {INTERVALS.map((it) => (
        <ToggleGroupItem key={it.key} value={it.key} className="h-7 px-2 text-[11px]">
          {it.label}
          {it.key === 'auto' && data && interval === 'auto' && <span className="ml-1 opacity-65">{data.interval}</span>}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
  const mixed = productCount > 1
  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <Panel
        title="Weight vs target"
        subtitle={subtitle}
        action={picker}
        csv={csv}
        expandable
        footer={
          <>
            <Legend items={WEIGHT_LEGEND} />
            <FooterStats
              items={[
                ['Mean', fmtG(k?.mean_g, 2)],
                ['Deviation', `${fmtSigned(k?.mean_dev_g, 2)} g`],
                [mixed ? 'SD vs target' : 'SD', fmtG(mixed ? k?.sd_vs_target_g : k?.sd_g, 2)],
              ]}
            />
          </>
        }
      >
        <WeightTrendChart points={points} />
      </Panel>
      <Panel
        title="Quality indicators"
        subtitle={subtitle}
        csv={csv}
        expandable
        footer={
          <>
            <Legend items={RATES_LEGEND} />
            <FooterStats
              items={[
                ['EGA', fmtPct(k?.ega_pct)],
                ['Over', fmtPct(k?.overweight_pct)],
                ['Under', fmtPct(k?.underweight_pct)],
                ['Feeding', fmtPct(k?.feeding_error_pct)],
              ]}
            />
          </>
        }
      >
        <RatesTrendChart points={points} />
      </Panel>
    </div>
  )
}

export function ThroughputPanel({
  filters,
  points,
  interval,
  k,
  scope,
  className,
}: {
  filters: FilterParams
  points: TrendPoint[] | undefined
  interval: string | undefined
  k: KPIs | undefined
  scope: string
  className?: string
}) {
  const active = (points ?? []).filter((p) => p.total > 0)
  const avg = active.length ? active.reduce((s, p) => s + p.total, 0) / active.length : null
  return (
    <Panel
      title="Throughput"
      subtitle={`${scope} · packs ${bucketText(interval)}`}
      className={className}
      csv={{ name: `throughput_${fileTag(filters)}`, rows: () => trendRows(points ?? []) }}
      expandable
      bodyClassName="pt-2 pb-2"
      footer={
        <>
          <Legend items={THROUGHPUT_LEGEND} />
          <FooterStats
            items={[
              ['Avg', fmtInt(avg)],
              ['Peak', fmtInt(active.length ? Math.max(...active.map((p) => p.total)) : null)],
              ['Total', fmtInt(k?.total)],
            ]}
          />
        </>
      }
    >
      <ThroughputChart points={points ?? []} />
    </Panel>
  )
}

export function HistogramPanel({
  filters,
  data,
  scope,
  className,
}: {
  filters: FilterParams
  data: Histogram | undefined
  scope: string
  className?: string
}) {
  const p = data?.product
  return (
    <Panel
      title="Weight distribution"
      subtitle={p ? `${scope} · ${productLabel(p)} · limits ${fmtNum(p.lo_g, 1)} – ${fmtNum(p.hi_g, 1)} g` : scope}
      className={className}
      csv={{ name: `distribution_${fileTag(filters)}`, rows: () => (data?.bins ?? []).map((b) => ({ from_g: b.lo, to_g: b.hi, packs: b.n })) }}
      expandable
      footer={
        <>
          <Legend items={HISTOGRAM_LEGEND} />
          <FooterStats
            items={[
              ['Target', fmtG(p?.target_g)],
              ['Packs', fmtInt(data?.total)],
            ]}
          />
        </>
      }
    >
      <HistogramChart data={data} />
    </Panel>
  )
}

export function LiveWeightsPanel({
  rows,
  product,
  tz,
  className,
}: {
  rows: Weighing[]
  product: Product | null | undefined
  tz?: string
  className?: string
}) {
  return (
    <Panel
      title="Live weights"
      subtitle={`Realtime · last ${fmtInt(rows.length)} packs · ${productLabel(product)}`}
      className={className}
      csv={{
        name: 'live-weights',
        rows: () => rows.map((r) => ({ ts: r.ts, seq: r.seq, judgement: r.judgement, weight_g: r.weight_g })),
      }}
      expandable
      footer={
        <>
          <Legend items={JUDGEMENT_LEGEND} />
          <FooterStats
            items={LIMITS.filter((l) => l.key !== 'lolo_g' && l.key !== 'hihi_g').map(
              (l) => [l.name, fmtNum(product?.[l.key], 1)] as [string, string],
            )}
          />
        </>
      }
    >
      <LiveWeightChart rows={rows} product={product} tz={tz} />
    </Panel>
  )
}
