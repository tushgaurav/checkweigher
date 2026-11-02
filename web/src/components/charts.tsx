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
import type { Histogram, TrendPoint, Weighing } from '@/lib/api'
import { fmtG, fmtInt, fmtNum, fmtPct, fmtTime } from '@/lib/format'
import { colorOf } from '@/lib/judgement'
import { LIMITS, RATE_SERIES, type LimitSet } from '@/lib/series'

const AXIS = {
  tick: { fill: 'var(--muted-foreground)', fontSize: 10.5, fontFamily: 'var(--font-sans)' },
  tickLine: false,
  axisLine: { stroke: 'var(--border)' },
} as const
const GRID = <CartesianGrid stroke="var(--hairline)" />

/** Fixed-height chart area that grows to fill a panel shown full screen. */
function ChartBox({ height, children }: { height: number; children: ReactNode }) {
  return (
    <div data-chart-box style={{ height }}>
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: -1, height }}>
        {children}
      </ResponsiveContainer>
    </div>
  )
}

function TipBox({ title, rows }: { title: ReactNode; rows: [string, ReactNode, string?][] }) {
  return (
    <div className="min-w-44 rounded-sm border border-border bg-popover px-3 py-2 text-[11px] text-popover-foreground shadow-md">
      <div className="mb-1.5 font-semibold">{title}</div>
      {rows.map(([label, value, color]) => (
        <div key={label} className="flex items-center gap-2 py-0.5">
          {color && <span className="size-2 shrink-0" style={{ backgroundColor: color }} />}
          <span className="text-muted-foreground">{label}</span>
          <span className="num ml-auto pl-4 font-medium">{value}</span>
        </div>
      ))}
    </div>
  )
}

export function Empty({ children, height = 160 }: { children: ReactNode; height?: number }) {
  return (
    <div
      className="flex items-center justify-center rounded-sm border border-dashed border-border text-xs text-muted-foreground"
      style={{ height }}
    >
      {children}
    </div>
  )
}

function limitLines(p: LimitSet | null | undefined, axis: 'x' | 'y') {
  if (!p) return null
  return LIMITS.filter((l) => p[l.key] != null).map((l) => (
    <ReferenceLine
      key={l.label}
      {...{ [axis]: p[l.key] }}
      stroke={l.color}
      strokeDasharray={l.dash || undefined}
      strokeWidth={l.key === 'target_g' ? 1.5 : 1}
      ifOverflow="extendDomain"
      label={{
        value: l.label,
        position: axis === 'x' ? 'top' : 'right',
        fill: l.color,
        fontSize: 9.5,
        fontWeight: 600,
        fontFamily: 'var(--font-sans)',
      }}
    />
  ))
}

export function HistogramChart({ data }: { data: Histogram | undefined }) {
  const p = data?.product
  const bins = (data?.bins ?? []).map((b) => ({ ...b, mid: (b.lo + b.hi) / 2 }))
  const zone = (mid: number) =>
    p?.lo_g != null && mid < p.lo_g ? 'var(--under)' : p?.hi_g != null && mid > p.hi_g ? 'var(--over)' : 'var(--ok)'
  if (!bins.length) return <Empty height={230}>No weighings in range</Empty>
  return (
    <ChartBox height={230}>
      <BarChart data={bins} margin={{ top: 16, right: 18, bottom: 0, left: 0 }} barCategoryGap={1}>
        {GRID}
        <XAxis
          dataKey="mid"
          type="number"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(v: number) => fmtNum(v, 0)}
          {...AXIS}
        />
        <YAxis {...AXIS} tickFormatter={(v: number) => fmtInt(v)} width={52} />
        <Tooltip
          cursor={{ fill: 'var(--hairline)' }}
          content={({ active, payload }) => {
            const b = active && payload?.[0]?.payload
            return b ? (
              <TipBox title={`${fmtNum(b.lo, 1)} – ${fmtNum(b.hi, 1)} g`} rows={[['Packs', fmtInt(b.n), zone(b.mid)]]} />
            ) : null
          }}
        />
        <Bar dataKey="n" isAnimationActive={false} radius={[1, 1, 0, 0]}>
          {bins.map((b) => (
            <Cell key={b.mid} fill={zone(b.mid)} />
          ))}
        </Bar>
        {limitLines(p, 'x')}
      </BarChart>
    </ChartBox>
  )
}

/** Mean weight with min–max envelope and the (possibly changing) target. */
export function WeightTrendChart({ points }: { points: TrendPoint[] }) {
  const data = points.map((p) => ({ ...p, band: p.min_g != null && p.max_g != null ? [p.min_g, p.max_g] : null }))
  if (!data.length) return <Empty height={250}>No data in range</Empty>
  return (
    <ChartBox height={250}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -6 }}>
        {GRID}
        <XAxis dataKey="label" {...AXIS} minTickGap={48} />
        <YAxis {...AXIS} domain={['auto', 'auto']} tickFormatter={(v: number) => fmtNum(v, 0)} width={52} />
        <Tooltip
          cursor={{ stroke: 'var(--muted-foreground)', strokeDasharray: '3 3' }}
          content={({ active, payload }) => {
            const p = active && (payload?.[0]?.payload as TrendPoint | undefined)
            return p ? (
              <TipBox
                title={p.label}
                rows={[
                  ['Mean', fmtG(p.mean_g, 2), 'var(--chart-1)'],
                  ['Target', fmtG(p.mean_target_g, 1), 'var(--signal)'],
                  ['SD', fmtG(p.sd_g, 2)],
                  ['Min – max', `${fmtNum(p.min_g, 1)} – ${fmtNum(p.max_g, 1)}`],
                  ['Packs', fmtInt(p.total)],
                ]}
              />
            ) : null
          }}
        />
        <Area dataKey="band" stroke="none" fill="var(--chart-1)" fillOpacity={0.16} isAnimationActive={false} />
        <Line
          dataKey="mean_target_g"
          type="stepAfter"
          stroke="var(--signal)"
          strokeWidth={1.5}
          strokeDasharray="5 3"
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
        <Line dataKey="mean_g" type="monotone" stroke="var(--chart-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ChartBox>
  )
}

export function RatesTrendChart({ points }: { points: TrendPoint[] }) {
  if (!points.length) return <Empty height={250}>No data in range</Empty>
  return (
    <ChartBox height={250}>
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
          cursor={{ stroke: 'var(--muted-foreground)', strokeDasharray: '3 3' }}
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
            strokeWidth={s.axis === 'ega' ? 2 : 1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ChartBox>
  )
}

export function ThroughputChart({ points, height = 190 }: { points: TrendPoint[]; height?: number }) {
  if (!points.length) return <Empty height={height}>No data in range</Empty>
  return (
    <ChartBox height={height}>
      <BarChart data={points} margin={{ top: 8, right: 4, bottom: 0, left: -6 }} barCategoryGap="14%">
        {GRID}
        <XAxis dataKey="label" {...AXIS} minTickGap={36} />
        <YAxis {...AXIS} tickFormatter={(v: number) => fmtInt(v)} width={48} />
        <Tooltip
          cursor={{ fill: 'var(--hairline)' }}
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
        <Bar dataKey="passed" stackId="t" fill="var(--ok)" isAnimationActive={false} />
        <Bar
          dataKey={(p: TrendPoint) => p.total - p.passed}
          stackId="t"
          fill="var(--reject)"
          radius={[1, 1, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ChartBox>
  )
}

/** Individual weights as they arrive, coloured by judgement, against the active limits. */
export function LiveWeightChart({ rows, product, tz }: { rows: Weighing[]; product: LimitSet | null | undefined; tz?: string }) {
  const data = rows
    .filter((r) => r.weight_g != null)
    .map((r) => ({ t: new Date(r.ts).getTime(), w: r.weight_g as number, j: r.judgement, seq: r.seq }))
  if (!data.length) return <Empty height={270}>Waiting for weighings…</Empty>
  return (
    <ChartBox height={270}>
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
            <Cell key={d.t} fill={colorOf(d.j)} r={2.75} />
          ))}
        </Scatter>
      </ScatterChart>
    </ChartBox>
  )
}
