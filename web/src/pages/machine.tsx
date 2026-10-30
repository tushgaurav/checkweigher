import { useParams } from 'react-router'
import { HistogramChart, LiveWeightChart } from '@/components/charts'
import { FilterBar } from '@/components/filter-bar'
import { KpiTiles } from '@/components/kpi-tiles'
import { Dot, Panel, Stat } from '@/components/panel'
import { ProductionPanel, StatsPanel } from '@/components/production'
import { EventList, WeighingsTable } from '@/components/tables'
import { TrendPanels } from '@/components/trend-panel'
import { useFilters } from '@/lib/filters'
import { fmtAgo, fmtG, fmtInt, productLabel } from '@/lib/format'
import { useLive, useLiveWeighings } from '@/lib/use-live'
import { useEvents, useHistogram, useMeta, useRecent, useSummary, useTrend } from '@/lib/queries'

function StateBadge({ label, state }: { label: string; state: string | null | undefined }) {
  const ok = state === 'connected'
  const color = state === 'disabled' ? 'var(--muted-foreground)' : ok ? 'var(--ok)' : 'var(--reject)'
  return (
    <span className="flex items-center gap-1.5 border border-border px-2 py-1 text-[11px]">
      <Dot color={color} />
      <span className="text-muted-foreground">{label}</span>
      <span>{state ?? 'unknown'}</span>
    </span>
  )
}

export function MachinePage() {
  const id = Number(useParams().id)
  const { data: meta } = useMeta()
  const { filters, includesToday } = useFilters(id)
  const { data: summary } = useSummary(filters, includesToday)
  const { data: allProducts } = useSummary({ ...filters, product: undefined }, includesToday)
  const { data: trend } = useTrend(filters, 'auto', includesToday)
  const { data: histogram } = useHistogram(filters, includesToday)
  const { data: recent } = useRecent(id)
  const { data: events } = useEvents(id)
  const live = useLiveWeighings(id, recent)
  const { status } = useLive()

  const machine = meta?.machines.find((m) => m.id === id)
  const ms = summary?.machines.find((m) => m.machine.id === id)
  const s = status[id]
  const k = ms?.kpis
  const productCount = summary?.products.length ?? 1
  const current = allProducts?.products.find((p) => p.id === s?.product_id) ?? histogram?.product
  const lastLive = live.at(-1)
  const last = includesToday && lastLive ? { ...lastLive, machine_id: id } : ms?.last

  return (
    <div className="flex flex-col gap-3">
      <div className="rise flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="signage text-[10.5px] text-muted-foreground">Checkweigher</div>
          <h1 className="signage mt-1 text-2xl text-foreground">
            {machine?.code ?? `#${id}`} <span className="text-muted-foreground">· {machine?.name}</span>
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StateBadge label="serial" state={s?.serial_state} />
          <StateBadge label="modbus" state={s?.modbus_state} />
          <span className="num border border-border px-2 py-1 text-[11px] text-muted-foreground">
            last line {fmtAgo(s?.last_line_at)}
          </span>
        </div>
      </div>

      <FilterBar products={allProducts?.products} machineId={id} />
      <KpiTiles k={k} trend={trend?.points} productCount={productCount} />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Panel
          i={5}
          title="Live weights"
          className="xl:col-span-2"
          action={<span className="num text-[11px] text-muted-foreground">last {fmtInt(live.length)} packs</span>}
        >
          <LiveWeightChart rows={live} product={current} tz={meta?.timezone} />
        </Panel>
        <Panel i={6} title="Active product">
          <div className="grid grid-cols-2 gap-4">
            <Stat label="Product" value={productLabel(current)} />
            <Stat label="Target" value={fmtG(current?.target_g)} tone="var(--signal)" />
            <Stat label="Hi limit" value={fmtG(current?.hi_g)} tone="var(--over)" />
            <Stat label="Lo limit" value={fmtG(current?.lo_g)} tone="var(--under)" />
            <Stat label="HiHi" value={fmtG(current?.hihi_g)} />
            <Stat label="LoLo" value={fmtG(current?.lolo_g)} />
          </div>
          {s?.device_counters && (
            <div className="num mt-5 border-t border-border pt-3 text-[11px] text-muted-foreground">
              Indicator summary counter: {fmtInt(Number(s.device_counters.total))} judged since last clear
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-5">
        <ProductionPanel i={7} k={k} completeness={ms?.completeness} className="lg:col-span-3" />
        <StatsPanel i={8} k={k} last={last} tz={meta?.timezone} productCount={productCount} className="lg:col-span-2" />
      </div>

      <TrendPanels filters={filters} includesToday={includesToday} i={9} />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-5">
        <Panel i={11} title="Weight distribution" className="xl:col-span-2">
          <HistogramChart data={histogram} />
        </Panel>
        <Panel i={12} title="Collector events" className="xl:col-span-3" bodyClassName="max-h-80 overflow-y-auto py-1">
          <EventList events={events} tz={meta?.timezone} />
        </Panel>
      </div>

      <Panel i={13} title="Weighings">
        <WeighingsTable filters={filters} tz={meta?.timezone} />
      </Panel>
    </div>
  )
}
