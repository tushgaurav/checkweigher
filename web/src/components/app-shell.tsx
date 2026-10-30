import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { Dot } from '@/components/panel'
import { fmtAgo, fmtG } from '@/lib/format'
import { colorOf } from '@/lib/judgement'
import { useLive } from '@/lib/use-live'
import { useMeta } from '@/lib/queries'
import { cn } from '@/lib/utils'

function Clock({ tz }: { tz?: string }) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  return (
    <span className="num text-xs text-muted-foreground">
      {now.toLocaleTimeString('en-IN', { hour12: false, timeZone: tz })}
    </span>
  )
}

function MachineChips() {
  const { data: meta } = useMeta()
  const { status, connected } = useLive()
  const location = useLocation()
  return (
    <div className="flex min-w-0 items-center gap-1.5 overflow-x-auto">
      {meta?.machines.map((m) => {
        const s = status[m.id]
        const online = !!s?.online
        return (
          <NavLink
            key={m.id}
            to={{ pathname: `/machines/${m.id}`, search: location.search }}
            className={({ isActive }) =>
              cn(
                'press flex shrink-0 items-center gap-2 border border-border px-2.5 py-1 text-xs transition-colors hover:bg-accent',
                isActive && 'border-signal/50 bg-accent',
              )
            }
            title={s ? `serial ${s.serial_state} · modbus ${s.modbus_state} · updated ${fmtAgo(s.updated_at)}` : 'no status'}
          >
            <Dot color={online ? 'var(--ok)' : 'var(--reject)'} live={online && connected} />
            <span className="font-medium">{m.code}</span>
            <span className="num text-muted-foreground" style={{ color: s ? colorOf(s.last_judgement) : undefined }}>
              {s?.last_weight_g != null ? fmtG(s.last_weight_g) : '—'}
            </span>
          </NavLink>
        )
      })}
    </div>
  )
}

export function AppShell() {
  const { data: meta } = useMeta()
  const location = useLocation()
  return (
    <div className="flex min-h-svh flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-6 px-4 md:px-6">
          <NavLink to={{ pathname: '/', search: location.search }} className="flex shrink-0 items-baseline gap-2">
            <span className="signage text-sm text-foreground">Checkweigher</span>
            <span className="signage text-[10px] text-signal">QA</span>
          </NavLink>
          <nav className="hidden items-center gap-1 text-xs sm:flex">
            <NavLink
              to={{ pathname: '/', search: location.search }}
              end
              className={({ isActive }) =>
                cn('px-2 py-1 text-muted-foreground transition-colors hover:text-foreground', isActive && 'text-foreground')
              }
            >
              Overview
            </NavLink>
          </nav>
          <div className="min-w-0 flex-1">
            <MachineChips />
          </div>
          <div className="hidden shrink-0 items-center gap-3 md:flex">
            <span className="text-xs text-muted-foreground">{meta?.plant_name}</span>
            {meta && (
              <span className="border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground">
                Shift <span className="text-foreground">{meta.current_shift}</span>
              </span>
            )}
            <Clock tz={meta?.timezone} />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-5 md:px-6">
        <Outlet />
      </main>
    </div>
  )
}
