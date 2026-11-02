import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router'
import { Dot, JudgementBadge, Panel } from '@/components/panel'
import type { MachineStatus, Product } from '@/lib/api'
import { fmtAgo, fmtG, fmtInt, productLabel } from '@/lib/format'
import { colorOf, kindOf } from '@/lib/judgement'
import { useLive } from '@/lib/use-live'
import { useMeta } from '@/lib/queries'

const LAMPS = [
  { kind: 'under', color: 'var(--under)' },
  { kind: 'ok', color: 'var(--ok)' },
  { kind: 'over', color: 'var(--over)' },
] as const

/** Side-view mimic of a checkweigher line: infeed, weigh and reject conveyors, the indicator
 * (mirroring the last weight and its LO/OK/HI lamp) and a stack light for the link state. */
function CheckweigherMimic({
  display,
  unit,
  judgement,
  online,
  label,
}: {
  display: string
  unit?: string
  judgement?: string | null
  online: boolean
  label: string
}) {
  const kind = kindOf(judgement)
  const tone = judgement ? colorOf(judgement) : 'var(--muted-foreground)'
  // Off-nominal judgements (feeding / metal) light the middle lamp in their own colour.
  const lit = (i: number) => (kind === LAMPS[i].kind ? LAMPS[i].color : i === 1 && (kind === 'feed' || kind === 'reject') ? tone : null)
  const stack = !online ? 0 : kind === 'ok' || !judgement ? 2 : 1
  const stackColors = ['var(--reject)', 'var(--over)', 'var(--ok)']
  const frame = 'var(--muted-foreground)'
  const conveyors = [
    { x: 12, w: 76 },
    { x: 100, w: 80 },
    { x: 192, w: 76 },
  ]
  return (
    <svg viewBox="0 0 280 160" className="w-full" role="img" aria-label={label}>
      <line x1="6" y1="154.5" x2="274" y2="154.5" stroke="var(--border)" strokeWidth="1.5" />
      {/* indicator stand + stack-light pole sit behind the belts */}
      <rect x="138" y="68" width="4" height="40" fill={frame} />
      <rect x="255" y="50" width="2.5" height="58" fill={frame} />
      {conveyors.map(({ x, w }) => (
        <g key={x}>
          <path d={`M${x + 12} 118V154M${x + w - 12} 118V154M${x + 7} 154h10M${x + w - 17} 154h10`} stroke={frame} strokeWidth="2" />
          <rect x={x} y="108" width={w} height="10" rx="5" fill="var(--muted)" stroke={frame} strokeWidth="1.25" />
          <circle cx={x + 5} cy="113" r="2.5" fill="var(--card)" stroke={frame} />
          <circle cx={x + w - 5} cy="113" r="2.5" fill="var(--card)" stroke={frame} />
        </g>
      ))}
      {/* load cell under the weigh conveyor */}
      <rect x="128" y="120" width="24" height="7" rx="1" fill="var(--signal)" />
      <rect x="136" y="127" width="8" height="27" fill="var(--muted)" stroke={frame} strokeWidth="1.25" />
      {/* upcoming pack, pack on the scale (coloured by judgement), pack leaving */}
      <rect x="35" y="90" width="30" height="18" rx="1.5" fill="none" stroke={frame} strokeDasharray="3 2" />
      <rect
        x="122"
        y="86"
        width="36"
        height="22"
        rx="1.5"
        fill={`color-mix(in oklch, ${tone} 20%, var(--card))`}
        stroke={tone}
        strokeWidth="1.5"
      />
      <rect x="130" y="93" width="20" height="5" rx="1" fill={tone} opacity="0.55" />
      <rect x="215" y="90" width="30" height="18" rx="1.5" fill="var(--muted)" stroke={frame} opacity="0.7" />
      {/* indicator */}
      <rect x="92" y="14" width="96" height="54" rx="3" fill="var(--card)" stroke="var(--foreground)" strokeWidth="1.5" />
      <rect x="100" y="21" width="80" height="27" rx="1.5" fill="var(--display)" />
      <text
        x={unit ? 166 : 174}
        y="40"
        textAnchor="end"
        className="mono"
        fontSize="14"
        fontWeight="500"
        fill="var(--display-foreground)"
      >
        {display}
      </text>
      {unit && (
        <text x="174" y="40" textAnchor="end" className="mono" fontSize="7" fill="var(--display-foreground)" opacity="0.75">
          {unit}
        </text>
      )}
      {LAMPS.map((l, i) => (
        <rect
          key={l.kind}
          x={108 + i * 24}
          y="54"
          width="16"
          height="5"
          rx="1"
          fill={lit(i) ?? 'var(--muted)'}
          stroke={lit(i) ? 'none' : 'var(--border)'}
        />
      ))}
      {/* stack light: red = offline, amber = last pack off-nominal, green = running in limits */}
      <rect x="249" y="10" width="14" height="3" rx="1" fill={frame} />
      {stackColors.map((c, i) => (
        <rect
          key={c}
          x="250"
          y={13 + i * 12}
          width="12"
          height="12"
          fill={stack === i ? c : `color-mix(in oklch, ${c} 18%, var(--card))`}
          stroke="var(--card)"
          strokeWidth="1"
        />
      ))}
    </svg>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 items-center justify-end gap-1.5 truncate text-right font-medium">{children}</dd>
    </>
  )
}

function LinkState({ state }: { state: string | null | undefined }) {
  const color = state === 'connected' ? 'var(--ok)' : state === 'disabled' ? 'var(--muted-foreground)' : 'var(--reject)'
  return (
    <>
      <Dot color={color} />
      {state ?? 'unknown'}
    </>
  )
}

function SingleMachine({ id, product }: { id: number; product?: Product | null }) {
  const { data: meta } = useMeta()
  const { status } = useLive()
  const m = meta?.machines.find((x) => x.id === id)
  const s: MachineStatus | undefined = status[id]
  const online = !!s?.online
  return (
    <Panel
      title={m ? `${m.code} · ${m.name}` : `Checkweigher #${id}`}
      subtitle={
        <span style={{ color: online ? 'var(--ok)' : 'var(--reject)' }} className="font-medium">
          {online ? 'Online' : 'Offline'}
          <span className="font-normal text-muted-foreground"> · {m?.mode ?? 'serial'} link</span>
        </span>
      }
      bodyClassName="flex flex-col justify-between gap-3 pt-2"
    >
      <CheckweigherMimic
        display={s?.last_weight_g != null ? s.last_weight_g.toFixed(1) : '----'}
        unit="g"
        judgement={s?.last_judgement}
        online={online}
        label={`${m?.code ?? id}: last weight ${fmtG(s?.last_weight_g)} ${s?.last_judgement ?? ''}`}
      />
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[11.5px]">
        <Row label="Last pack">
          <JudgementBadge code={s?.last_judgement} />
          <span className="num">{fmtAgo(s?.last_ts)}</span>
        </Row>
        <Row label="Product">
          <span className="num">
            {productLabel(product)} · {fmtG(product?.target_g)}
          </span>
        </Row>
        <Row label="Serial">
          <LinkState state={s?.serial_state} />
        </Row>
        <Row label="Modbus">
          <LinkState state={s?.modbus_state} />
        </Row>
        {s?.device_counters && (
          <Row label="Indicator count">
            <span className="num" title="Products judged since the indicator's summary was last cleared">
              {fmtInt(Number(s.device_counters.total))}
            </span>
          </Row>
        )}
      </dl>
    </Panel>
  )
}

function LineCard() {
  const { data: meta } = useMeta()
  const { status } = useLive()
  const location = useLocation()
  const machines = meta?.machines ?? []
  const online = machines.filter((m) => status[m.id]?.online).length
  return (
    <Panel title="Checkweighers" subtitle={`${online} of ${machines.length} online`} bodyClassName="flex flex-col gap-3 pt-2">
      <CheckweigherMimic
        display={`${online}/${machines.length}`}
        unit="on"
        online={online > 0}
        label={`${online} of ${machines.length} checkweighers online`}
      />
      <ul className="flex flex-col text-[11.5px]">
        {machines.map((m) => {
          const s = status[m.id]
          return (
            <li key={m.id} className="border-t border-border first:border-0">
              <Link
                to={{ pathname: `/machines/${m.id}`, search: location.search }}
                className="flex items-center gap-2 py-1.5 hover:text-primary"
              >
                <Dot color={s?.online ? 'var(--ok)' : 'var(--reject)'} />
                <span className="font-semibold">{m.code}</span>
                <span className="truncate text-muted-foreground">{m.name}</span>
                <span className="num ml-auto">{fmtG(s?.last_weight_g)}</span>
                <JudgementBadge code={s?.last_judgement} />
              </Link>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}

/** Machine card at the head of a page: the mimic for one checkweigher, or the line when several are in scope. */
export function MachineCard({ machineId, product }: { machineId?: number; product?: Product | null }) {
  const { data: meta } = useMeta()
  const id = machineId ?? (meta?.machines.length === 1 ? meta.machines[0].id : undefined)
  return id !== undefined ? <SingleMachine id={id} product={product} /> : <LineCard />
}
