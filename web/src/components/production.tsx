import { Panel, Stat } from '@/components/panel'
import type { Completeness, KPIs, LastWeight } from '@/lib/api'
import { fmtAgo, fmtG, fmtInt, fmtKg, fmtNum, fmtPct, fmtTime } from '@/lib/format'
import { colorOf } from '@/lib/judgement'

type Segment = { key: string; label: string; value: number; color: string }

/** Totals + a single stacked bar of where every judged product went. */
export function ProductionPanel({
  k,
  completeness,
  i,
  className,
}: {
  k: KPIs | undefined
  completeness?: Completeness | null
  i: number
  className?: string
}) {
  const total = k?.total ?? 0
  const segments: Segment[] = k
    ? [
        { key: 'ok', label: 'Passed', value: k.passed, color: 'var(--ok)' },
        { key: 'over', label: 'Overweight', value: k.overweight, color: 'var(--over)' },
        { key: 'under', label: 'Underweight', value: k.underweight, color: 'var(--under)' },
        { key: 'feed', label: 'Feeding error', value: k.feeding_errors, color: 'var(--feed)' },
        { key: 'reject', label: 'Metal / external', value: k.metal + k.external, color: 'var(--reject)' },
      ]
    : []

  return (
    <Panel
      i={i}
      title="Production"
      className={className}
      action={
        completeness?.pct != null && (
          <span
            className="num text-[11px] text-muted-foreground"
            title={`${fmtInt(completeness.received)} of ${fmtInt(completeness.expected)} products counted by the indicator were received`}
          >
            data capture{' '}
            <span style={{ color: completeness.pct >= 99.5 ? 'var(--ok)' : 'var(--over)' }}>
              {fmtPct(completeness.pct, 1)}
            </span>
          </span>
        )
      }
    >
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-4">
        <Stat label="Products judged" value={fmtInt(k?.total)} sub={`${fmtInt(k?.weighed)} weighed`} />
        <Stat label="Passed" value={fmtInt(k?.passed)} tone="var(--ok)" sub={fmtKg(k?.passed_kg)} />
        <Stat label="Total quantity" value={fmtNum(k?.quantity_kg, 1)} sub="kg weighed" />
        <Stat
          label="Rejected"
          value={fmtInt(k?.rejected)}
          tone="var(--reject)"
          sub={k?.rejected_pct != null ? fmtPct(k.rejected_pct) : undefined}
        />
      </div>

      <div className="mt-5 flex h-2.5 w-full overflow-hidden bg-muted">
        {total > 0 &&
          segments
            .filter((s) => s.value > 0)
            .map((s) => (
              <div
                key={s.key}
                title={`${s.label}: ${fmtInt(s.value)} (${fmtPct((s.value / total) * 100)})`}
                style={{ width: `${(s.value / total) * 100}%`, backgroundColor: s.color }}
                className="h-full min-w-px transition-[width] duration-500 ease-[var(--ease-out-strong)]"
              />
            ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3 lg:grid-cols-5">
        {segments.map((s) => (
          <div key={s.key} className="flex items-center gap-2 text-[11px]">
            <span className="size-2 shrink-0" style={{ backgroundColor: s.color }} />
            <span className="truncate text-muted-foreground">{s.label}</span>
            <span className="num ml-auto">{fmtInt(s.value)}</span>
          </div>
        ))}
      </div>

      {k && (
        <div className="num mt-4 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-border pt-3 text-[11px] text-muted-foreground sm:grid-cols-4">
          <span>Detect two {fmtInt(k.detect_two)}</span>
          <span>Unsplit {fmtInt(k.unsplit)}</span>
          <span>Feeding err {fmtPct(k.feeding_error_pct)}</span>
          <span>Metal {fmtInt(k.metal)}</span>
        </div>
      )}
    </Panel>
  )
}

export function StatsPanel({
  k,
  last,
  tz,
  i,
  productCount = 1,
  className,
}: {
  k: KPIs | undefined
  last: LastWeight | null | undefined
  tz?: string
  i: number
  productCount?: number
  className?: string
}) {
  return (
    <Panel
      i={i}
      title="Statistics"
      className={className}
      action={
        productCount > 1 && (
          <span className="text-[11px] text-over" title="Mean, median and mode span different targets. Filter one product.">
            {productCount} products mixed
          </span>
        )
      }
    >
      <div className="flex items-end justify-between gap-4 border-b border-border pb-4">
        <div className="min-w-0">
          <div className="text-[11px] tracking-wide text-muted-foreground uppercase">Last weight</div>
          <div className="readout mt-1 text-[2.6rem] leading-none" style={{ color: colorOf(last?.judgement) }}>
            {last?.weight_g != null ? fmtNum(last.weight_g, 1) : '—'}
            <span className="num ml-1.5 text-sm text-muted-foreground">g</span>
          </div>
        </div>
        {last && (
          <div className="num text-right text-[11px] text-muted-foreground">
            <div className="text-foreground" style={{ color: colorOf(last.judgement) }}>
              {last.judgement}
            </div>
            <div>{fmtTime(last.ts, tz)}</div>
            <div>{fmtAgo(last.ts)}</div>
          </div>
        )}
      </div>
      <div className="mt-4 grid grid-cols-3 gap-x-4 gap-y-4">
        <Stat label="Mean" value={fmtG(k?.mean_g, 2)} />
        <Stat label="Median" value={fmtG(k?.median_g, 1)} />
        <Stat label="Mode" value={fmtG(k?.mode_g, 1)} sub={k?.mode_count ? `× ${fmtInt(k.mode_count)}` : undefined} />
        <Stat label="Min" value={fmtG(k?.min_g, 1)} />
        <Stat label="Max" value={fmtG(k?.max_g, 1)} />
        <Stat label="Avg target" value={fmtG(k?.mean_target_g, 1)} />
      </div>
    </Panel>
  )
}
