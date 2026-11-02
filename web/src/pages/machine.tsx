import { useParams } from 'react-router'
import { HistogramPanel, LiveWeightsPanel, ThroughputPanel, TrendPanels } from '@/components/chart-panels'
import { FilterBar } from '@/components/filter-bar'
import { KpiStack, TotalsStack } from '@/components/kpi-tiles'
import { MachineCard } from '@/components/machine-card'
import { Panel } from '@/components/panel'
import { ProductionPanel, StatsPanel } from '@/components/production'
import { EventList, WeighingsPanel } from '@/components/tables'
import { useFilters } from '@/lib/filters'
import { HEAD_GRID } from '@/lib/layout'
import { useLive, useLiveWeighings } from '@/lib/use-live'
import { useEvents, useHistogram, useMeta, useRecent, useSummary, useTrend } from '@/lib/queries'

export function MachinePage() {
  const id = Number(useParams().id)
  const { data: meta } = useMeta()
  const { filters, includesToday, scope } = useFilters(id)
  const { data: summary } = useSummary(filters, includesToday)
  const { data: allProducts } = useSummary({ ...filters, product: undefined }, includesToday)
  const { data: trend } = useTrend(filters, 'auto', includesToday)
  const { data: histogram } = useHistogram(filters, includesToday)
  const { data: recent } = useRecent(id)
  const { data: events } = useEvents(id)
  const live = useLiveWeighings(id, recent)
  const { status } = useLive()

  const ms = summary?.machines.find((m) => m.machine.id === id)
  const s = status[id]
  const k = ms?.kpis
  const productCount = summary?.products.length ?? 1
  const current = allProducts?.products.find((p) => p.id === s?.product_id) ?? histogram?.product
  const lastLive = live.at(-1)
  const last = includesToday && lastLive ? { ...lastLive, machine_id: id } : ms?.last

  return (
    <div className="flex flex-col gap-3">
      <FilterBar products={allProducts?.products} machineId={id} />
      <div className={HEAD_GRID}>
        <MachineCard machineId={id} product={current} />
        <KpiStack k={k} productCount={productCount} />
        <TotalsStack k={k} />
        <ThroughputPanel filters={filters} points={trend?.points} interval={trend?.interval} k={k} scope={scope} />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <LiveWeightsPanel rows={live} product={current} tz={meta?.timezone} className="xl:col-span-2" />
        <StatsPanel k={k} last={last} tz={meta?.timezone} scope={scope} productCount={productCount} />
      </div>

      <TrendPanels filters={filters} includesToday={includesToday} scope={scope} k={k} productCount={productCount} />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_minmax(0,1fr)]">
        <ProductionPanel k={k} completeness={ms?.completeness} scope={scope} />
        <HistogramPanel filters={filters} data={histogram} scope={scope} />
        <Panel
          title="Collector events"
          subtitle="Latest 30 · link, sequence and product changes"
          className="lg:col-span-2 xl:col-span-1"
          bodyClassName="max-h-80 overflow-y-auto px-0 pt-1 pb-1"
        >
          <EventList events={events} tz={meta?.timezone} />
        </Panel>
      </div>

      <WeighingsPanel filters={filters} tz={meta?.timezone} scope={scope} />
    </div>
  )
}
