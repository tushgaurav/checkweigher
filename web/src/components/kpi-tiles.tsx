import { ArrowDownToLine, ArrowUpFromLine, Gauge, Sigma, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cardClass } from '@/components/panel'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { KPIs } from '@/lib/api'
import { fmtG, fmtInt, fmtKg, fmtNum, fmtPct, fmtSigned } from '@/lib/format'
import { cn } from '@/lib/utils'

type MetricProps = {
  icon: LucideIcon
  label: string
  definition: string
  value: ReactNode
  unit?: string
  tone: string
  detail: ReactNode
}

/** Icon + label on the left, headline value on the right (panel-meter style). */
function MetricTile({ icon: Icon, label, definition, value, unit, tone, detail }: MetricProps) {
  return (
    <section className={cn('flex min-w-0 items-center gap-3 px-4 py-3', cardClass)}>
      <span
        className="grid size-9 shrink-0 place-items-center rounded-sm"
        style={{ color: tone, backgroundColor: `color-mix(in oklch, ${tone} 13%, transparent)` }}
      >
        <Icon className="size-[18px]" strokeWidth={1.9} />
      </span>
      <div className="min-w-0 flex-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <h3 className="w-fit cursor-help text-[13.5px] leading-5 font-semibold decoration-muted-foreground/50 decoration-dotted underline-offset-4 hover:underline">
              {label}
            </h3>
          </TooltipTrigger>
          <TooltipContent className="max-w-72 text-xs leading-relaxed">{definition}</TooltipContent>
        </Tooltip>
        <p className="num truncate text-[11px] leading-4 text-muted-foreground">{detail}</p>
      </div>
      <div className="flex shrink-0 items-baseline gap-1">
        <span className="readout text-[26px] leading-none">{value}</span>
        {unit && <span className="text-[13px] font-medium text-muted-foreground">{unit}</span>}
      </div>
    </section>
  )
}

/** `productCount` > 1 means several targets are mixed: the raw SD is then dominated by the
 * difference between products, so the deviation-from-target SD becomes the headline. */
export function KpiStack({ k, productCount = 1 }: { k: KPIs | undefined; productCount?: number }) {
  const mixed = productCount > 1
  return (
    <div className="grid min-w-0 auto-rows-fr gap-3">
      <MetricTile
        icon={Gauge}
        label="EGA"
        definition="Excess give-away: Σ(weight − target) of accepted packs ÷ Σ target × 100. Volume-weighted across machines and shifts. (Definition pending client confirmation.)"
        value={fmtNum(k?.ega_pct, 2)}
        unit="%"
        tone="var(--signal)"
        detail={
          <>
            {fmtG(k?.ega_g_per_pack, 2)} per pack · {fmtKg(k?.giveaway_kg)} given away
          </>
        }
      />
      <MetricTile
        icon={ArrowUpFromLine}
        label="Overweight"
        definition="Products judged Hi or HiHi ÷ all products judged."
        value={fmtNum(k?.overweight_pct, 2)}
        unit="%"
        tone="var(--over)"
        detail={
          <>
            {fmtInt(k?.overweight)} packs · {fmtInt(k?.overweight_hihi)} over HiHi
          </>
        }
      />
      <MetricTile
        icon={ArrowDownToLine}
        label="Underweight"
        definition="Products judged Lo or LoLo ÷ all products judged."
        value={fmtNum(k?.underweight_pct, 2)}
        unit="%"
        tone="var(--under)"
        detail={
          <>
            {fmtInt(k?.underweight)} packs · {fmtInt(k?.underweight_lolo)} under LoLo
          </>
        }
      />
      <MetricTile
        icon={Sigma}
        label={mixed ? 'Std deviation · vs target' : 'Std deviation'}
        definition={
          mixed
            ? `${productCount} products with different targets are selected, so this is the SD of (weight − target). Filter one product to see the plain weight SD.`
            : 'Sample standard deviation of individual weights.'
        }
        value={fmtNum(mixed ? k?.sd_vs_target_g : k?.sd_g, 2)}
        unit="g"
        tone="var(--chart-1)"
        detail={
          mixed ? (
            <>
              {productCount} products · mean deviation {fmtSigned(k?.mean_dev_g, 2)} g
            </>
          ) : (
            <>
              mean {fmtG(k?.mean_g, 2)} · deviation {fmtSigned(k?.mean_dev_g, 2)} g
            </>
          )
        }
      />
    </div>
  )
}

function TotalTile({ label, value, unit, sub, tone }: { label: string; value: ReactNode; unit?: string; sub?: ReactNode; tone?: string }) {
  return (
    <section className={cn('flex min-w-0 flex-col items-center justify-center px-3 py-2.5 text-center', cardClass)}>
      <div className="flex items-baseline gap-1">
        <span className="readout text-[24px] leading-tight" style={tone ? { color: tone } : undefined}>
          {value}
        </span>
        {unit && <span className="text-xs font-medium text-muted-foreground">{unit}</span>}
      </div>
      <div className="truncate text-[11.5px] text-muted-foreground">
        {label}
        {sub != null && <span className="num"> · {sub}</span>}
      </div>
    </section>
  )
}

/** Production counters, stacked like the cumulative totals of a flow meter. */
export function TotalsStack({ k }: { k: KPIs | undefined }) {
  const passedPct = k && k.total ? (k.passed / k.total) * 100 : null
  return (
    <div className="grid min-w-0 auto-rows-fr gap-3">
      <TotalTile label="Products judged" value={fmtInt(k?.total)} sub={`${fmtInt(k?.weighed)} weighed`} />
      <TotalTile label="Passed" value={fmtInt(k?.passed)} sub={fmtPct(passedPct, 1)} tone="var(--ok)" />
      <TotalTile
        label="Rejected"
        value={fmtInt(k?.rejected)}
        sub={fmtPct(k?.rejected_pct)}
        tone={k?.rejected ? 'var(--reject)' : undefined}
      />
      <TotalTile label="Quantity weighed" value={fmtNum(k?.quantity_kg, 1)} unit="kg" sub={`${fmtKg(k?.passed_kg)} passed`} />
    </div>
  )
}
