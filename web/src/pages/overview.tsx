import { HistogramPanel, ThroughputPanel, TrendPanels } from '@/components/chart-panels'
import { FilterBar } from '@/components/filter-bar'
import { KpiStack, TotalsStack } from '@/components/kpi-tiles'
import { MachineCard } from '@/components/machine-card'
import { Panel } from '@/components/panel'
import { ProductionPanel, StatsPanel } from '@/components/production'
import { MachineTable } from '@/components/tables'
import { useFilters } from '@/lib/filters'
import { HEAD_GRID } from '@/lib/layout'
import { useLive } from '@/lib/use-live'
import { useHistogram, useMeta, useSummary, useTrend } from '@/lib/queries'

export function OverviewPage() {
  const { data: meta } = useMeta()
  const { status } = useLive()
  const { filters, includesToday, scope } = useFilters()
  const { data: summary, error } = useSummary(filters, includesToday)
  const { data: allProducts } = useSummary({ ...filters, product: undefined }, includesToday)
  const { data: trend } = useTrend(filters, 'auto', includesToday)
  const { data: histogram } = useHistogram(filters, includesToday)
  const k = summary?.overall
  const productCount = summary?.products.length ?? 1
  const single = filters.machine?.length === 1 ? filters.machine[0] : meta?.machines.length === 1 ? meta.machines[0].id : undefined
  const product = single !== undefined ? allProducts?.products.find((p) => p.id === status[single]?.product_id) : undefined

  return (
    <div className="flex flex-col gap-3">
      <FilterBar products={allProducts?.products} />
      {error && (
        <div className="rounded-sm border border-reject/40 bg-reject/8 px-4 py-2 text-xs text-reject">{error.message}</div>
      )}
      <div className={HEAD_GRID}>
        <MachineCard machineId={single} product={product} />
        <KpiStack k={k} productCount={productCount} />
        <TotalsStack k={k} />
        <ThroughputPanel filters={filters} points={trend?.points} interval={trend?.interval} k={k} scope={scope} />
      </div>
      <TrendPanels filters={filters} includesToday={includesToday} scope={scope} k={k} productCount={productCount} />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.4fr)]">
        <ProductionPanel k={k} completeness={summary?.completeness} scope={scope} />
        <StatsPanel k={k} last={summary?.last} tz={meta?.timezone} scope={scope} productCount={productCount} />
        <HistogramPanel filters={filters} data={histogram} scope={scope} className="lg:col-span-2 xl:col-span-1" />
      </div>
      <Panel title="Checkweighers" subtitle={scope} bodyClassName="px-0 pb-1">
        <MachineTable rows={summary?.machines ?? []} />
      </Panel>
    </div>
  )
}
