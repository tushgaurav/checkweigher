import { FooterStats, JudgementBadge, Panel, Stat, Swatch } from '@/components/panel'
import type { Completeness, KPIs, LastWeight } from '@/lib/api'
import { fmtAgo, fmtG, fmtInt, fmtNum, fmtPct, fmtTime } from '@/lib/format'
import { colorOf } from '@/lib/judgement'

type Segment = { key: string; label: string; value: number; color: string }

/** Where every judged product went: one stacked bar + a count/share table. */
export function ProductionPanel({
  k,
  completeness,
  scope,
  className,
}: {
  k: KPIs | undefined
  completeness?: Completeness | null
  scope: string
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
      title="Judgement breakdown"
      subtitle={scope}
      className={className}
      action={
        completeness?.pct != null && (
          <span
            className="num text-[11px] text-muted-foreground"
            title={
              completeness.pct > 100.5
                ? `${fmtInt(completeness.received)} records for ${fmtInt(completeness.expected)} products counted by the indicator: duplicates`
                : `${fmtInt(completeness.received)} of ${fmtInt(completeness.expected)} products counted by the indicator were received`
            }
          >
            Data capture{' '}
            <span
              className="font-semibold"
              style={{ color: Math.abs(completeness.pct - 100) <= 0.5 ? 'var(--ok)' : 'var(--over)' }}
            >
              {fmtPct(completeness.pct, 1)}
            </span>
          </span>
        )
      }
      footer={
        k && (
          <FooterStats
            items={[
              ['Detect two', fmtInt(k.detect_two)],
              ['Unsplit', fmtInt(k.unsplit)],
              ['Metal', fmtInt(k.metal)],
              ['External', fmtInt(k.external)],
            ]}
          />
        )
      }
    >
      <div className="flex h-3 w-full overflow-hidden rounded-sm bg-muted">
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

      <table className="mt-3 w-full text-[12px]">
        <tbody>
          {segments.map((s) => (
            <tr key={s.key} className="border-b border-border last:border-0">
              <td className="py-1.5">
                <span className="flex items-center gap-2">
                  <Swatch color={s.color} />
                  {s.label}
                </span>
              </td>
              <td className="num py-1.5 text-right font-semibold">{fmtInt(s.value)}</td>
              <td className="num w-20 py-1.5 text-right text-muted-foreground">
                {total ? fmtPct((s.value / total) * 100) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  )
}

export function StatsPanel({
  k,
  last,
  tz,
  scope,
  productCount = 1,
  className,
}: {
  k: KPIs | undefined
  last: LastWeight | null | undefined
  tz?: string
  scope: string
  productCount?: number
  className?: string
}) {
  return (
    <Panel
      title="Statistics"
      subtitle={scope}
      className={className}
      action={
        productCount > 1 && (
          <span
            className="rounded-sm bg-over/12 px-1.5 py-0.5 text-[11px] font-medium text-over"
            title="Mean, median and mode span different targets. Filter one product."
          >
            {productCount} products mixed
          </span>
        )
      }
    >
      <div className="flex items-end justify-between gap-4 rounded-sm bg-muted px-3 py-3">
        <div className="min-w-0">
          <div className="text-[11px] text-muted-foreground">Last weight</div>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="readout text-[34px] leading-none" style={{ color: colorOf(last?.judgement) }}>
              {last?.weight_g != null ? fmtNum(last.weight_g, 1) : '—'}
            </span>
            <span className="text-sm font-medium text-muted-foreground">g</span>
          </div>
        </div>
        {last && (
          <div className="num flex flex-col items-end gap-1 text-[11px] text-muted-foreground">
            <JudgementBadge code={last.judgement} />
            <span>
              {fmtTime(last.ts, tz)} · {fmtAgo(last.ts)}
            </span>
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
