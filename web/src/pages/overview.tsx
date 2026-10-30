import { HistogramChart } from '@/components/charts'
import { FilterBar } from '@/components/filter-bar'
import { KpiTiles } from '@/components/kpi-tiles'
import { Panel } from '@/components/panel'
import { ProductionPanel, StatsPanel } from '@/components/production'
import { MachineTable } from '@/components/tables'
import { TrendPanels } from '@/components/trend-panel'
import { useFilters } from '@/lib/filters'
import { useHistogram, useMeta, useSummary, useTrend } from '@/lib/queries'

export function OverviewPage() {
  const { data: meta } = useMeta()
  const { filters, includesToday } = useFilters()
  const { data: summary, error } = useSummary(filters, includesToday)
  const { data: allProducts } = useSummary({ ...filters, product: undefined }, includesToday)
  const { data: trend } = useTrend(filters, 'auto', includesToday)
  const { data: histogram } = useHistogram(filters, includesToday)
  const k = summary?.overall
  const productCount = summary?.products.length ?? 1

  return (
    <div className="flex flex-col gap-3">
      <FilterBar products={allProducts?.products} />
      {error && (
        <div className="border border-reject/40 bg-reject/10 px-4 py-2 text-xs text-reject">{error.message}</div>
      )}
      <KpiTiles k={k} trend={trend?.points} productCount={productCount} />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-5">
        <ProductionPanel i={5} k={k} completeness={summary?.completeness} className="lg:col-span-3" />
        <StatsPanel i={6} k={k} last={summary?.last} tz={meta?.timezone} productCount={productCount} className="lg:col-span-2" />
      </div>
      <TrendPanels filters={filters} includesToday={includesToday} i={7} />
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-5">
        <Panel i={9} title="Weight distribution" className="xl:col-span-2">
          <HistogramChart data={histogram} />
        </Panel>
        <Panel i={10} title="Checkweighers" className="xl:col-span-3" bodyClassName="p-0">
          <MachineTable rows={summary?.machines ?? []} />
        </Panel>
      </div>
    </div>
  )
}
