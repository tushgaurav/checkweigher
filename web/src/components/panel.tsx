import { FileDown, Maximize2, Minimize2 } from 'lucide-react'
import { useRef, type ReactNode, type RefObject } from 'react'
import { Button } from '@/components/ui/button'
import { downloadCsv } from '@/lib/csv'
import { useFullscreen } from '@/lib/fullscreen'
import { kindOf, KIND_VAR } from '@/lib/judgement'
import type { LegendItem } from '@/lib/series'
import { cn } from '@/lib/utils'

type PanelProps = {
  title: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  /** legend / summary row under the body */
  footer?: ReactNode
  /** offer what the panel shows as a CSV download */
  csv?: { name: string; rows: () => Record<string, unknown>[] }
  /** allow blowing the panel up to full screen */
  expandable?: boolean
  className?: string
  bodyClassName?: string
  children: ReactNode
}

export const cardClass = 'rounded-sm border border-border bg-card shadow-xs'

/** Dashboard card: title + data scope, header tools, body, legend/summary footer. */
export function Panel({ title, subtitle, action, footer, csv, expandable, className, bodyClassName, children }: PanelProps) {
  const ref = useRef<HTMLElement>(null)
  return (
    <section ref={ref} data-panel className={cn('flex min-w-0 flex-col', cardClass, className)}>
      <header className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 px-4 pt-3">
        <div className="min-w-0">
          <h2 className="truncate text-[13.5px] leading-5 font-semibold">{title}</h2>
          {subtitle && <p className="num truncate text-[11px] leading-4 text-muted-foreground">{subtitle}</p>}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {action}
          {csv && (
            <ToolButton label="Download CSV" onClick={() => downloadCsv(csv.name, csv.rows())}>
              <FileDown />
            </ToolButton>
          )}
          {expandable && <ExpandButton target={ref} />}
        </div>
      </header>
      <div data-panel-body className={cn('flex-1 px-4 pt-3 pb-4', bodyClassName)}>
        {children}
      </div>
      {footer && (
        <footer className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 px-4 pb-3">{footer}</footer>
      )}
    </section>
  )
}

export function ToolButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <Button
      size="icon-sm"
      variant="ghost"
      className="press text-muted-foreground hover:text-foreground"
      title={label}
      aria-label={label}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}

function ExpandButton({ target }: { target: RefObject<HTMLElement | null> }) {
  const { active, toggle, supported } = useFullscreen(target)
  if (!supported) return null
  return (
    <ToolButton label={active ? 'Exit full screen' : 'Full screen'} onClick={toggle}>
      {active ? <Minimize2 /> : <Maximize2 />}
    </ToolButton>
  )
}

export function Swatch({ color, shape = 'square' }: Pick<LegendItem, 'color' | 'shape'>) {
  if (shape === 'line') return <span className="h-0.5 w-3.5 shrink-0" style={{ backgroundColor: color }} />
  if (shape === 'dash') return <span className="w-3.5 shrink-0 border-t-2 border-dashed" style={{ borderColor: color }} />
  return <span className={cn('size-2 shrink-0', shape === 'dot' && 'rounded-full')} style={{ backgroundColor: color }} />
}

export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-1.5">
          <Swatch color={it.color} shape={it.shape} />
          {it.label}
        </li>
      ))}
    </ul>
  )
}

/** Right-aligned "Avg / Total" style figures in a panel footer. */
export function FooterStats({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="ml-auto flex items-end gap-5 text-right">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[10.5px] leading-4 text-muted-foreground">{label}</dt>
          <dd className="num text-[12.5px] leading-4 font-semibold">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Stat({
  label,
  value,
  sub,
  tone,
  className,
}: {
  label: ReactNode
  value: ReactNode
  sub?: ReactNode
  tone?: string
  className?: string
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1', className)}>
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="readout truncate text-lg leading-none" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      {sub && <span className="num truncate text-[11px] text-muted-foreground">{sub}</span>}
    </div>
  )
}

export function Dot({ color, live, className }: { color: string; live?: boolean; className?: string }) {
  return (
    <span
      className={cn('inline-block size-2 shrink-0 rounded-full', live && 'live-dot', className)}
      style={{ backgroundColor: color, color }}
    />
  )
}

/** Indicator judgement code as a tinted chip (OK, HI, LO, TD, MD...). */
export function JudgementBadge({ code, className }: { code: string | null | undefined; className?: string }) {
  if (!code) return null
  const tone = KIND_VAR[kindOf(code)]
  return (
    <span
      className={cn('inline-flex min-w-7 justify-center rounded-sm px-1.5 py-px text-[10.5px] leading-4 font-semibold', className)}
      style={{ color: tone, backgroundColor: `color-mix(in oklch, ${tone} 14%, transparent)` }}
    >
      {code}
    </span>
  )
}
