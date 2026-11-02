import { ChevronLeft, ChevronRight, ChevronsLeft, Sheet } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { Dot, JudgementBadge, Panel } from '@/components/panel'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { exportUrl, type Event, type FilterParams, type MachineSummary } from '@/lib/api'
import { fmtAgo, fmtDateTime, fmtG, fmtInt, fmtNum, fmtPct, fmtSigned } from '@/lib/format'
import { useLive } from '@/lib/use-live'
import { useWeighings } from '@/lib/queries'
import { cn } from '@/lib/utils'

export function MachineTable({ rows }: { rows: MachineSummary[] }) {
  const { status } = useLive()
  const location = useLocation()
  return (
    <Table className="text-[12px]">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Checkweigher</TableHead>
          <TableHead className="text-right">Judged</TableHead>
          <TableHead className="text-right">EGA %</TableHead>
          <TableHead className="text-right">Over %</TableHead>
          <TableHead className="text-right">Under %</TableHead>
          <TableHead className="text-right">SD g</TableHead>
          <TableHead className="text-right">Mean g</TableHead>
          <TableHead className="text-right">Feed err</TableHead>
          <TableHead className="text-right">Last weight</TableHead>
          <TableHead className="text-right">Capture</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(({ machine, kpis: k, last, completeness }) => {
          const s = status[machine.id]
          return (
            <TableRow key={machine.id} className="group">
              <TableCell>
                <Link
                  to={{ pathname: `/machines/${machine.id}`, search: location.search }}
                  className="flex items-center gap-2.5 group-hover:text-primary"
                >
                  <Dot color={s?.online ? 'var(--ok)' : 'var(--reject)'} />
                  <span className="font-semibold">{machine.code}</span>
                  <span className="text-muted-foreground">{machine.name}</span>
                </Link>
              </TableCell>
              <TableCell className="num text-right font-medium">{fmtInt(k.total)}</TableCell>
              <TableCell className="num text-right">{fmtNum(k.ega_pct, 2)}</TableCell>
              <TableCell className="num text-right">{fmtNum(k.overweight_pct, 2)}</TableCell>
              <TableCell className="num text-right">{fmtNum(k.underweight_pct, 2)}</TableCell>
              <TableCell className="num text-right">{fmtNum(k.sd_g, 2)}</TableCell>
              <TableCell className="num text-right">{fmtNum(k.mean_g, 1)}</TableCell>
              <TableCell className="num text-right">{fmtInt(k.feeding_errors)}</TableCell>
              <TableCell className="num text-right" title={last ? fmtAgo(last.ts) : ''}>
                <span className="inline-flex items-center gap-2">
                  {fmtG(last?.weight_g)}
                  <JudgementBadge code={last?.judgement} />
                </span>
              </TableCell>
              <TableCell className="num text-right text-muted-foreground">{fmtPct(completeness?.pct, 1)}</TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

const JUDGEMENT_FILTERS = [
  { key: 'all', label: 'All', codes: [] as string[] },
  { key: 'rejects', label: 'Rejects', codes: ['HH', 'HI', 'LO', 'LL', 'TD', 'US', 'MD', 'E1', 'E2'] },
  { key: 'over', label: 'Over', codes: ['HH', 'HI'] },
  { key: 'under', label: 'Under', codes: ['LO', 'LL'] },
  { key: 'feed', label: 'Feeding', codes: ['TD', 'US'] },
]

/** Paged log of individual weighings (newest first) with judgement filter and Excel export. */
export function WeighingsPanel({ filters, tz, scope }: { filters: FilterParams; tz?: string; scope: string }) {
  const [pages, setPages] = useState<string[]>([])
  const [jf, setJf] = useState('all')
  const codes = JUDGEMENT_FILTERS.find((f) => f.key === jf)?.codes ?? []
  const before = pages.at(-1)
  const { data, isFetching } = useWeighings(filters, before, codes, 25)

  return (
    <Panel
      title="Weighings"
      subtitle={`${scope} · newest first`}
      bodyClassName="px-0 pb-1"
      action={
        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={0}
            value={jf}
            aria-label="Judgement"
            onValueChange={(v) => {
              if (!v) return
              setJf(v)
              setPages([])
            }}
          >
            {JUDGEMENT_FILTERS.map((f) => (
              <ToggleGroupItem key={f.key} value={f.key} className="h-7 px-2.5 text-[11px]">
                {f.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <div className="flex items-center gap-1">
            <span className="num mr-1 text-[11px] text-muted-foreground">Page {pages.length + 1}</span>
            <Button size="icon-sm" variant="outline" disabled={!pages.length} onClick={() => setPages([])} title="Newest">
              <ChevronsLeft />
            </Button>
            <Button size="icon-sm" variant="outline" disabled={!pages.length} onClick={() => setPages((p) => p.slice(0, -1))} title="Newer">
              <ChevronLeft />
            </Button>
            <Button
              size="icon-sm"
              variant="outline"
              disabled={!data?.next_before}
              onClick={() => data?.next_before && setPages((p) => [...p, data.next_before as string])}
              title="Older"
            >
              <ChevronRight />
            </Button>
          </div>
          <Button asChild size="icon-sm" variant="ghost" className="text-muted-foreground hover:text-foreground" title="Export Excel">
            <a href={exportUrl(filters)} download aria-label="Export Excel">
              <Sheet />
            </a>
          </Button>
        </div>
      }
    >
      <div className={cn('transition-opacity', isFetching && 'opacity-60')}>
        <Table className="text-[12px]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Timestamp</TableHead>
              <TableHead>Shift</TableHead>
              <TableHead className="text-right">Seq</TableHead>
              <TableHead>Judgement</TableHead>
              <TableHead className="text-right">Weight g</TableHead>
              <TableHead className="text-right">Target g</TableHead>
              <TableHead className="text-right">Deviation g</TableHead>
              <TableHead>Source</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.rows.map((r) => (
              <TableRow key={`${r.machine_id}-${r.ts}`} className="even:bg-muted/50">
                <TableCell className="num">{fmtDateTime(r.ts, tz)}</TableCell>
                <TableCell>{r.shift_code}</TableCell>
                <TableCell className="num text-right text-muted-foreground">{r.seq ?? '—'}</TableCell>
                <TableCell>
                  <JudgementBadge code={r.judgement} />
                </TableCell>
                <TableCell className="num text-right font-semibold">{fmtNum(r.weight_g, 1)}</TableCell>
                <TableCell className="num text-right text-muted-foreground">{fmtNum(r.target_g, 1)}</TableCell>
                <TableCell className="num text-right">
                  {r.weight_g != null && r.target_g != null ? fmtSigned(r.weight_g - r.target_g, 1) : '—'}
                </TableCell>
                <TableCell className="text-muted-foreground">{r.source}</TableCell>
              </TableRow>
            ))}
            {data && !data.rows.length && (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                  No weighings match
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </Panel>
  )
}

const EVENT_TONE: Record<string, string> = {
  seq_gap: 'var(--over)',
  counter_reset: 'var(--feed)',
  summary_cleared: 'var(--feed)',
  parse_error: 'var(--reject)',
  serial_disconnected: 'var(--reject)',
  modbus_disconnected: 'var(--reject)',
  serial_connected: 'var(--ok)',
  modbus_connected: 'var(--ok)',
  product: 'var(--signal)',
}

export function EventList({ events, tz }: { events: Event[] | undefined; tz?: string }) {
  if (!events?.length) return <p className="px-4 py-3 text-xs text-muted-foreground">No collector events.</p>
  return (
    <ol className="flex flex-col">
      {events.map((e) => (
        <li key={e.id} className="flex gap-3 border-b border-border px-4 py-2 text-[12px] last:border-0">
          <span
            className="mt-1 h-3 w-1 shrink-0 rounded-full"
            style={{ backgroundColor: EVENT_TONE[e.kind] ?? 'var(--muted-foreground)' }}
          />
          <div className="min-w-0 flex-1">
            <div className="truncate">{e.message}</div>
            <div className="num text-[11px] text-muted-foreground">
              {e.kind.replaceAll('_', ' ')} · {fmtDateTime(e.ts, tz)}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}
