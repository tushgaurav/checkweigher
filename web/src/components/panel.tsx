import type { CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/utils'

type PanelProps = {
  title: ReactNode
  action?: ReactNode
  className?: string
  bodyClassName?: string
  /** stagger index for the page-load entrance */
  i?: number
  children: ReactNode
}

/** Instrument-panel section: hairline frame, corner ticks, signage label. */
export function Panel({ title, action, className, bodyClassName, i = 0, children }: PanelProps) {
  return (
    <section
      className={cn('rise ticks relative flex min-w-0 flex-col border border-border bg-card/85', className)}
      style={{ '--i': i } as CSSProperties}
    >
      <header className="flex min-h-10 items-center justify-between gap-3 border-b border-border px-4 py-2">
        <h2 className="signage text-[10.5px] text-muted-foreground">{title}</h2>
        {action}
      </header>
      <div className={cn('flex-1 p-4', bodyClassName)}>{children}</div>
    </section>
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
      <span className="text-[11px] tracking-wide text-muted-foreground uppercase">{label}</span>
      <span className="readout truncate text-xl leading-none" style={tone ? { color: tone } : undefined}>
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
