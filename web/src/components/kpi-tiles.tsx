import type { CSSProperties, ReactNode } from 'react'
import { Area, AreaChart, ResponsiveContainer, YAxis } from 'recharts'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { KPIs, TrendPoint } from '@/lib/api'
import { fmtG, fmtInt, fmtKg, fmtNum, fmtSigned } from '@/lib/format'

type TileProps = {
  label: string
  definition: string
  value: ReactNode
  unit?: string
  tone: string
  detail: ReactNode
  spark?: (number | null)[]
  i: number
}

function Sparkline({ data, tone }: { data: (number | null)[]; tone: string }) {
  const points = data.map((v, x) => ({ x, v }))
  if (points.filter((p) => p.v != null).length < 2) return <div className="h-10" />
  const id = `spark-${tone.replace(/[^a-z]/gi, '')}`
  return (
    <ResponsiveContainer width="100%" height={40}>
      <AreaChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={tone} stopOpacity={0.28} />
            <stop offset="100%" stopColor={tone} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={['dataMin', 'dataMax']} />
        <Area
          type="monotone"
          dataKey="v"
          stroke={tone}
          strokeWidth={1.25}
          fill={`url(#${id})`}
          isAnimationActive={false}
          connectNulls
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function Tile({ label, definition, value, unit, tone, detail, spark, i }: TileProps) {
  return (
    <section
      className="rise ticks relative flex min-w-0 flex-col justify-between gap-3 border border-border bg-card/85 p-4"
      style={{ '--i': i } as CSSProperties}
    >
      <div className="flex items-center justify-between gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <h3 className="signage cursor-help text-[10.5px] text-muted-foreground decoration-dotted underline-offset-4 hover:underline">
              {label}
            </h3>
          </TooltipTrigger>
          <TooltipContent className="max-w-72 text-xs leading-relaxed">{definition}</TooltipContent>
        </Tooltip>
        <span className="h-px w-8" style={{ backgroundColor: tone }} />
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="readout text-[2.6rem] leading-none" style={{ color: tone }}>
          {value}
        </span>
        {unit && <span className="num text-sm text-muted-foreground">{unit}</span>}
      </div>
      <div className="num text-[11px] leading-relaxed text-muted-foreground">{detail}</div>
      {spark && <Sparkline data={spark} tone={tone} />}
    </section>
  )
}

/** `productCount` > 1 means several targets are mixed: the raw SD is then dominated by the
 * difference between products, so the deviation-from-target SD becomes the headline. */
export function KpiTiles({
  k,
  trend,
  productCount = 1,
}: {
  k: KPIs | undefined
  trend: TrendPoint[] | undefined
  productCount?: number
}) {
  const t = trend ?? []
  const mixed = productCount > 1
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Tile
        i={1}
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
        spark={t.map((p) => p.ega_pct)}
      />
      <Tile
        i={2}
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
        spark={t.map((p) => p.overweight_pct)}
      />
      <Tile
        i={3}
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
        spark={t.map((p) => p.underweight_pct)}
      />
      <Tile
        i={4}
        label={mixed ? 'Std deviation · vs target' : 'Std deviation'}
        definition={
          mixed
            ? `${productCount} products with different targets are selected, so this is the SD of (weight − target). Filter one product to see the plain weight SD.`
            : 'Sample standard deviation of individual weights.'
        }
        value={fmtNum(mixed ? k?.sd_vs_target_g : k?.sd_g, 2)}
        unit="g"
        tone="var(--foreground)"
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
        spark={t.map((p) => (mixed ? p.sd_vs_target_g : p.sd_g))}
      />
    </div>
  )
}
