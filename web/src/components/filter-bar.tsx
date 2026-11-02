import { parseISO } from 'date-fns'
import { CalendarRange, Download } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { DateRange } from 'react-day-picker'
import { Dot } from '@/components/panel'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { exportUrl, type Product } from '@/lib/api'
import { PRESETS, activePreset, iso, rangeLabel, useFilters } from '@/lib/filters'
import { productLabel, fmtG } from '@/lib/format'
import { useLive } from '@/lib/use-live'
import { useMeta } from '@/lib/queries'
import { cn } from '@/lib/utils'

const ALL = 'all'

function DateRangePicker() {
  const { filters, update, todayDate } = useFilters()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<DateRange | undefined>()
  const active = activePreset(filters.from, filters.to, todayDate)

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (o) setDraft({ from: parseISO(filters.from), to: parseISO(filters.to) })
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" className="press h-9 min-w-60 justify-start gap-2.5 px-3 text-xs">
          <CalendarRange className="text-primary" />
          <span className="num font-semibold">{rangeLabel(filters.from, filters.to)}</span>
          {active && <span className="ml-auto font-normal text-muted-foreground">{active.label}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="flex w-auto gap-0 p-0">
        <div className="flex w-36 flex-col border-r border-border p-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => {
                const [a, b] = p.range(todayDate)
                update({ from: iso(a), to: iso(b) })
                setOpen(false)
              }}
              className={cn(
                'px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-muted',
                active?.key === p.key && 'bg-primary text-primary-foreground hover:bg-primary/90',
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="p-1">
          <Calendar
            mode="range"
            numberOfMonths={2}
            weekStartsOn={1}
            defaultMonth={draft?.from}
            selected={draft}
            disabled={{ after: todayDate }}
            onSelect={(r) => {
              setDraft(r)
              if (r?.from && r.to && iso(r.from) !== iso(r.to)) {
                update({ from: iso(r.from), to: iso(r.to) })
                setOpen(false)
              }
            }}
          />
          <div className="flex items-center justify-between gap-2 border-t border-border px-2 py-2">
            <span className="text-[11px] text-muted-foreground">Production dates (night shift counts on its start date)</span>
            <Button
              size="sm"
              disabled={!draft?.from}
              onClick={() => {
                if (!draft?.from) return
                update({ from: iso(draft.from), to: iso(draft.to ?? draft.from) })
                setOpen(false)
              }}
            >
              Apply
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function InfoBox({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex h-9 items-center gap-2 border border-input bg-card px-3 text-xs dark:bg-input/30', className)}>
      <span className="text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}

function Clock({ tz }: { tz?: string }) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  return (
    <span className="num text-muted-foreground">
      {now.toLocaleString('en-IN', {
        hour12: false,
        timeZone: tz,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })}
    </span>
  )
}

/** Plant-wide (overview) or single-machine data link state + plant clock. */
function LiveStatus({ machineId }: { machineId?: number }) {
  const { data: meta } = useMeta()
  const { status, connected } = useLive()
  const machines = meta?.machines ?? []
  const online = machines.filter((m) => status[m.id]?.online).length
  const [text, tone] = !connected
    ? ['Disconnected', 'var(--reject)']
    : machineId !== undefined
      ? status[machineId]?.online
        ? ['Online', 'var(--ok)']
        : ['Offline', 'var(--reject)']
      : online === machines.length
        ? ['Live', 'var(--ok)']
        : online === 0
          ? ['Offline', 'var(--reject)']
          : [`${machines.length - online} offline`, 'var(--over)']
  return (
    <InfoBox label="Status">
      <span className="flex items-center gap-1.5 font-semibold" style={{ color: tone }}>
        <Dot color={tone} live={tone === 'var(--ok)'} />
        {text}
      </span>
      <Clock tz={meta?.timezone} />
    </InfoBox>
  )
}

/** Toolbar row: data scope on the left, export + plant/link status on the right. */
export function FilterBar({ products, machineId }: { products?: Product[]; machineId?: number }) {
  const { data: meta } = useMeta()
  const { filters, update } = useFilters(machineId)
  const showMachine = machineId === undefined
  const machineValue = filters.machine?.length === 1 ? String(filters.machine[0]) : ALL

  return (
    <div className="flex flex-wrap items-center gap-2">
      <DateRangePicker />

      <ToggleGroup
        type="single"
        variant="outline"
        spacing={0}
        value={filters.shift ?? ALL}
        onValueChange={(v) => update({ shift: !v || v === ALL ? undefined : v })}
        className="h-9"
        aria-label="Shift"
      >
        <ToggleGroupItem value={ALL} className="h-9 px-3 text-xs">
          All shifts
        </ToggleGroupItem>
        {meta?.shifts.map((s) => (
          <ToggleGroupItem
            key={s.code}
            value={s.code}
            className="h-9 px-3 text-xs"
            title={`${s.name}: ${s.start_time.slice(0, 5)}–${s.end_time.slice(0, 5)}`}
          >
            Shift {s.code}
            <span className="num ml-1 hidden text-[10.5px] font-normal opacity-65 lg:inline">{s.start_time.slice(0, 5)}</span>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      {showMachine && meta && meta.machines.length > 1 && (
        <Select
          value={machineValue}
          onValueChange={(v) => update({ machine: v === ALL ? undefined : [Number(v)] })}
        >
          <SelectTrigger className="h-9 min-w-40 text-xs" aria-label="Checkweigher">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All checkweighers</SelectItem>
            {meta.machines.map((m) => (
              <SelectItem key={m.id} value={String(m.id)}>
                {m.code} · {m.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {products && products.length > 0 && (
        <Select
          value={filters.product ? String(filters.product) : ALL}
          onValueChange={(v) => update({ product: v === ALL ? undefined : Number(v) })}
        >
          <SelectTrigger className="h-9 min-w-44 text-xs" aria-label="Product">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All products</SelectItem>
            {products.map((p) => (
              <SelectItem key={p.id} value={String(p.id)}>
                <span className="num">{productLabel(p)}</span>
                <span className="text-muted-foreground">target {fmtG(p.target_g)}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <div className="ml-auto flex flex-wrap items-center gap-2">
        <Button asChild className="press h-9 gap-2 px-4 text-xs font-semibold tracking-wide uppercase">
          <a href={exportUrl(filters)} download>
            <Download />
            Export Excel
          </a>
        </Button>
        {meta && (
          <InfoBox label="Plant" className="hidden md:flex">
            <span className="font-semibold">{meta.plant_name}</span>
            <span className="text-muted-foreground">· Shift {meta.current_shift}</span>
          </InfoBox>
        )}
        <LiveStatus machineId={machineId} />
      </div>
    </div>
  )
}
