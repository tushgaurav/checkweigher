import type { ReactNode } from 'react'
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Histogram, Product, TrendPoint, Weighing } from '@/lib/api'
import { fmtG, fmtInt, fmtNum, fmtPct, fmtTime, productLabel } from '@/lib/format'
import { colorOf } from '@/lib/judgement'

const AXIS = {
  tick: { fill: 'var(--muted-foreground)', fontSize: 10, fontFamily: 'var(--font-mono)' },
  tickLine: false,
  axisLine: { stroke: 'var(--border)' },
} as const
const GRID = <CartesianGrid stroke="var(--hairline)" vertical={false} />

function TipBox({ title, rows }: { title: ReactNode; rows: [string, ReactNode, string?][] }) {
  return (
    <div className="min-w-44 border border-border bg-popover/95 px-3 py-2 text-[11px] shadow-xl backdrop-blur">
      <div className="mb-1.5 text-muted-foreground">{title}</div>
      {rows.map(([label, value, color]) => (
        <div key={label} className="flex items-center gap-2 py-0.5">
          {color && <span className="size-2 shrink-0" style={{ backgroundColor: color }} />}
          <span className="text-muted-foreground">{label}</span>
          <span className="num ml-auto pl-4">{value}</span>
        </div>
      ))}
    </div>
  )
}

type LimitSet = Pick<Product, 'target_g' | 'hi_g' | 'lo_g' | 'hihi_g' | 'lolo_g'>

function limitLines(p: LimitSet | null | undefined, axis: 'x' | 'y') {
  if (!p) return null
  const lines: [number | null | undefined, string, string, string][] = [
    [p.lolo_g, 'LL', 'var(--under)', '2 4'],
    [p.lo_g, 'LO', 'var(--under)', '5 3'],
    [p.target_g, 'T', 'var(--signal)', ''],
    [p.hi_g, 'HI', 'var(--over)', '5 3'],
    [p.hihi_g, 'HH', 'var(--over)', '2 4'],
  ]
  return lines
    .filter(([v]) => v != null)
    .map(([v, label, color, dash]) => (
      <ReferenceLine
        key={label}
        {...{ [axis]: v }}
        stroke={color}
        strokeDasharray={dash || undefined}
        strokeOpacity={0.8}
        ifOverflow="extendDomain"
        label={{
          value: label,
          position: axis === 'x' ? 'top' : 'right',
          fill: color,
          fontSize: 9,
          fontFamily: 'var(--font-mono)',
        }}
      />
    ))
}

export function HistogramChart({ data }: { data: Histogram | undefined }) {
  const p = data?.product
  const bins = (data?.bins ?? []).map((b) => ({ ...b, mid: (b.lo + b.hi) / 2 }))
  const zone = (mid: number) =>
    p?.lo_g != null && mid < p.lo_g ? 'var(--under)' : p?.hi_g != null && mid > p.hi_g ? 'var(--over)' : 'var(--ok)'
  if (!bins.length) return <Empty>No weighings in range</Empty>
  return (
    <div>
      <div className="num mb-2 flex flex-wrap gap-x-4 text-[11px] text-muted-foreground">
        <span>
          Product <span className="text-foreground">{productLabel(p)}</span>
        </span>
        <span>target {fmtG(p?.target_g)}</span>
        <span>
          limits {fmtG(p?.lo_g)} – {fmtG(p?.hi_g)}
        </span>
        <span className="ml-auto">{fmtInt(data?.total)} packs</span>
      </div>
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={bins} margin={{ top: 16, right: 18, bottom: 0, left: 0 }} barCategoryGap={1}>
          {GRID}
          <XAxis
            dataKey="mid"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(v: number) => fmtNum(v, 0)}
            {...AXIS}
          />
          <YAxis {...AXIS} tickFormatter={(v: number) => fmtInt(v)} width={56} />
          <Tooltip
            cursor={{ fill: 'var(--accent)' }}
            content={({ active, payload }) => {
              const b = active && payload?.[0]?.payload
              return b ? (
                <TipBox
                  title={`${fmtNum(b.lo, 1)} – ${fmtNum(b.hi, 1)} g`}
                  rows={[['Packs', fmtInt(b.n), zone(b.mid)]]}
                />
              ) : null
            }}
          />
          <Bar dataKey="n" isAnimationActive={false}>
            {bins.map((b) => (
              <Cell key={b.mid} fill={zone(b.mid)} fillOpacity={0.85} />
            ))}
          </Bar>
          {limitLines(p, 'x')}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-40 items-center justify-center border border-dashed border-border text-xs text-muted-foreground">
      {children}
    </div>
  )
}

/** Mean weight with min–max envelope and the (possibly changing) target. */
export function WeightTrendChart({ points }: { points: TrendPoint[] }) {
  const data = points.map((p) => ({ ...p, band: p.min_g != null && p.max_g != null ? [p.min_g, p.max_g] : null }))
  if (!data.length) return <Empty>No data in range</Empty>
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -6 }}>
        {GRID}
        <XAxis dataKey="label" {...AXIS} minTickGap={48} />
        <YAxis {...AXIS} domain={['auto', 'auto']} tickFormatter={(v: number) => fmtNum(v, 0)} width={52} />
        <Tooltip
          cursor={{ stroke: 'var(--border)' }}
          content={({ active, payload }) => {
            const p = active && (payload?.[0]?.payload as TrendPoint | undefined)
            return p ? (
              <TipBox
                title={p.label}
                rows={[
                  ['Mean', fmtG(p.mean_g, 2), 'var(--foreground)'],
                  ['Target', fmtG(p.mean_target_g, 1), 'var(--signal)'],
                  ['SD', fmtG(p.sd_g, 2)],
                  ['Min – max', `${fmtNum(p.min_g, 1)} – ${fmtNum(p.max_g, 1)}`, 'var(--muted-foreground)'],
                  ['Packs', fmtInt(p.total)],
                ]}
              />
            ) : null
          }}
        />
        <Area dataKey="band" stroke="none" fill="var(--foreground)" fillOpacity={0.07} isAnimationActive={false} />
        <Line
          dataKey="mean_target_g"
          type="stepAfter"
          stroke="var(--signal)"
          strokeWidth={1}
          strokeDasharray="4 3"
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
        <Line dataKey="mean_g" type="monotone" stroke="var(--foreground)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// EGA is typically well under 1 % while reject rates can be tens of %: EGA gets its own axis.
const RATE_SERIES = [
  { key: 'ega_pct', label: 'EGA', color: 'var(--signal)', axis: 'ega' },
  { key: 'overweight_pct', label: 'Overweight', color: 'var(--over)', axis: 'rate' },
  { key: 'underweight_pct', label: 'Underweight', color: 'var(--under)', axis: 'rate' },
  { key: 'feeding_error_pct', label: 'Feeding error', color: 'var(--feed)', axis: 'rate' },
] as const

export function RatesTrendChart({ points }: { points: TrendPoint[] }) {
  if (!points.length) return <Empty>No data in range</Empty>
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {RATE_SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="h-0.5 w-3" style={{ backgroundColor: s.color }} />
            {s.label} %{s.axis === 'ega' && <span className="text-[10px]">(right axis)</span>}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={216}>
        <LineChart data={points} margin={{ top: 8, right: 0, bottom: 0, left: -6 }}>
          {GRID}
          <XAxis dataKey="label" {...AXIS} minTickGap={48} />
          <YAxis yAxisId="rate" {...AXIS} domain={[0, 'auto']} tickFormatter={(v: number) => fmtNum(v, 1)} width={44} />
          <YAxis
            yAxisId="ega"
            orientation="right"
            {...AXIS}
            tick={{ ...AXIS.tick, fill: 'var(--signal)' }}
            domain={[(min: number) => Math.min(0, min), 'auto']}
            tickFormatter={(v: number) => fmtNum(v, 2)}
            width={44}
          />
          <Tooltip
            cursor={{ stroke: 'var(--border)' }}
            content={({ active, payload }) => {
              const p = active && (payload?.[0]?.payload as TrendPoint | undefined)
              return p ? (
                <TipBox
                  title={p.label}
                  rows={RATE_SERIES.map((s) => [s.label, fmtPct(p[s.key]), s.color] as [string, string, string])}
                />
              ) : null
            }}
          />
          {RATE_SERIES.map((s) => (
            <Line
              key={s.key}
              yAxisId={s.axis}
              dataKey={s.key}
              type="monotone"
              stroke={s.color}
              strokeWidth={1.4}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ThroughputChart({ points }: { points: TrendPoint[] }) {
  if (!points.length) return null
  return (
    <ResponsiveContainer width="100%" height={110}>
      <BarChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: -6 }} barCategoryGap="12%">
        <XAxis dataKey="label" {...AXIS} minTickGap={48} />
        <YAxis {...AXIS} tickFormatter={(v: number) => fmtInt(v)} width={52} />
        <Tooltip
          cursor={{ fill: 'var(--accent)' }}
          content={({ active, payload }) => {
            const p = active && (payload?.[0]?.payload as TrendPoint | undefined)
            return p ? (
              <TipBox
                title={p.label}
                rows={[
                  ['Judged', fmtInt(p.total)],
                  ['Passed', fmtInt(p.passed), 'var(--ok)'],
                  ['Rejected', fmtPct(p.rejected_pct), 'var(--reject)'],
                ]}
              />
            ) : null
          }}
        />
        <Bar dataKey="passed" stackId="t" fill="var(--ok)" fillOpacity={0.55} isAnimationActive={false} />
        <Bar
          dataKey={(p: TrendPoint) => p.total - p.passed}
          stackId="t"
          fill="var(--reject)"
          fillOpacity={0.7}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Individual weights as they arrive, coloured by judgement, against the active limits. */
export function LiveWeightChart({ rows, product, tz }: { rows: Weighing[]; product: LimitSet | null | undefined; tz?: string }) {
  const data = rows
    .filter((r) => r.weight_g != null)
    .map((r) => ({ t: new Date(r.ts).getTime(), w: r.weight_g as number, j: r.judgement, seq: r.seq }))
  if (!data.length) return <Empty>Waiting for weighings…</Empty>
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ScatterChart margin={{ top: 10, right: 22, bottom: 0, left: -6 }}>
        {GRID}
        <XAxis
          dataKey="t"
          type="number"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(v: number) => fmtTime(new Date(v).toISOString(), tz)}
          {...AXIS}
          minTickGap={40}
        />
        <YAxis dataKey="w" type="number" domain={['auto', 'auto']} {...AXIS} tickFormatter={(v: number) => fmtNum(v, 0)} width={52} />
        <Tooltip
          cursor={false}
          content={({ active, payload }) => {
            const d = active && payload?.[0]?.payload
            return d ? (
              <TipBox
                title={`#${d.seq ?? '—'} · ${fmtTime(new Date(d.t).toISOString(), tz)}`}
                rows={[[d.j, fmtG(d.w, 1), colorOf(d.j)]]}
              />
            ) : null
          }}
        />
        {limitLines(product, 'y')}
        <Scatter data={data} isAnimationActive={false} shape="circle">
          {data.map((d) => (
            <Cell key={d.t} fill={colorOf(d.j)} fillOpacity={0.9} r={2.5} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
