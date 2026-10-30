import { useState } from 'react'
import { RatesTrendChart, ThroughputChart, WeightTrendChart } from '@/components/charts'
import { Panel } from '@/components/panel'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { FilterParams } from '@/lib/api'
import { useTrend } from '@/lib/queries'

const INTERVALS = [
  { key: 'auto', label: 'Auto' },
  { key: '15m', label: '15m' },
  { key: '1h', label: '1h' },
  { key: 'shift', label: 'Shift' },
  { key: '1d', label: 'Day' },
]

export function TrendPanels({ filters, includesToday, i }: { filters: FilterParams; includesToday: boolean; i: number }) {
  const [interval, setIntervalKey] = useState('auto')
  const { data } = useTrend(filters, interval, includesToday)
  const points = data?.points ?? []
  const picker = (
    <ToggleGroup
      type="single"
      variant="outline"
      spacing={0}
      value={interval}
      onValueChange={(v) => v && setIntervalKey(v)}
    >
      {INTERVALS.map((it) => (
        <ToggleGroupItem key={it.key} value={it.key} className="h-6 px-2 text-[10.5px]">
          {it.label}
          {it.key === 'auto' && data && interval === 'auto' && (
            <span className="ml-1 text-muted-foreground">{data.interval}</span>
          )}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <Panel i={i} title="Weight vs target" action={picker}>
        <WeightTrendChart points={points} />
        <div className="mt-3 border-t border-border pt-2">
          <div className="mb-1 text-[10.5px] tracking-wide text-muted-foreground uppercase">Throughput</div>
          <ThroughputChart points={points} />
        </div>
      </Panel>
      <Panel i={i + 1} title="Quality indicators">
        <RatesTrendChart points={points} />
      </Panel>
    </div>
  )
}
