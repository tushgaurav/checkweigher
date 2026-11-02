import { Maximize, Minimize, Moon, Sun } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { Dot } from '@/components/panel'
import { fmtAgo, fmtG } from '@/lib/format'
import { useFullscreen } from '@/lib/fullscreen'
import { useLive } from '@/lib/use-live'
import { useMeta } from '@/lib/queries'
import { setTheme, useTheme, type Theme } from '@/lib/theme'
import { cn } from '@/lib/utils'

// Status lamps on the brand bar need more luminance than the in-panel tokens.
const LAMP_ON = 'oklch(0.86 0.18 150)'
const LAMP_OFF = 'oklch(0.76 0.16 25)'

function LogoMark() {
  return (
    <svg viewBox="0 0 32 32" className="size-7 shrink-0" aria-hidden>
      <rect width="32" height="32" rx="4" fill="var(--brand-foreground)" />
      <rect x="9" y="6" width="14" height="8" rx="1" fill="none" stroke="var(--brand)" strokeWidth="2" />
      <path d="M16 14v4" stroke="var(--brand)" strokeWidth="2" />
      <path d="M5 21h22" stroke="var(--brand)" strokeWidth="3" strokeLinecap="round" />
      <path d="M9 22v5M23 22v5" stroke="var(--brand)" strokeWidth="2" />
    </svg>
  )
}

function Tab({ to, end, title, children }: { to: string; end?: boolean; title?: string; children: ReactNode }) {
  const location = useLocation()
  return (
    <NavLink
      to={{ pathname: to, search: location.search }}
      end={end}
      title={title}
      className={({ isActive }) =>
        cn(
          'relative flex h-12 shrink-0 items-center gap-2 px-3 text-[12.5px] font-medium text-brand-foreground/75 transition-colors hover:bg-white/8 hover:text-brand-foreground',
          isActive &&
            'bg-white/12 text-brand-foreground after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-brand-foreground',
        )
      }
    >
      {children}
    </NavLink>
  )
}

function MachineTabs() {
  const { data: meta } = useMeta()
  const { status, connected } = useLive()
  return (
    <>
      {meta?.machines.map((m) => {
        const s = status[m.id]
        const online = !!s?.online
        return (
          <Tab
            key={m.id}
            to={`/machines/${m.id}`}
            title={s ? `serial ${s.serial_state} · modbus ${s.modbus_state} · updated ${fmtAgo(s.updated_at)}` : 'no status'}
          >
            <Dot color={online ? LAMP_ON : LAMP_OFF} live={online && connected} />
            {m.code}
            <span className="num font-normal opacity-75">{s?.last_weight_g != null ? fmtG(s.last_weight_g) : '—'}</span>
          </Tab>
        )
      })}
    </>
  )
}

const barButton =
  'press grid size-8 place-items-center text-brand-foreground/80 transition-colors hover:bg-white/10 hover:text-brand-foreground [&_svg]:size-4'

function ThemeSwitch() {
  const theme = useTheme()
  const options: [Theme, string, ReactNode][] = [
    ['light', 'Light theme', <Sun key="sun" />],
    ['dark', 'Dark theme', <Moon key="moon" />],
  ]
  return (
    <div role="group" aria-label="Colour theme" className="flex border border-white/20">
      {options.map(([value, label, icon]) => (
        <button
          key={value}
          type="button"
          aria-pressed={theme === value}
          aria-label={label}
          title={label}
          onClick={() => setTheme(value)}
          className={cn(barButton, 'size-7', theme === value && 'bg-white/18 text-brand-foreground')}
        >
          {icon}
        </button>
      ))}
    </div>
  )
}

function FullscreenButton() {
  const { active, toggle, supported } = useFullscreen()
  if (!supported) return null
  const label = active ? 'Exit full screen' : 'Full screen'
  return (
    <button type="button" onClick={toggle} title={label} aria-label={label} className={barButton}>
      {active ? <Minimize /> : <Maximize />}
    </button>
  )
}

export function AppShell() {
  const location = useLocation()
  return (
    <div className="flex min-h-svh flex-col">
      <header className="sticky top-0 z-30 bg-brand text-brand-foreground shadow-sm">
        <div className="mx-auto flex h-12 max-w-[1600px] items-center gap-4 px-4 md:px-6">
          <NavLink to={{ pathname: '/', search: location.search }} className="flex shrink-0 items-center gap-2.5">
            <LogoMark />
            <span className="hidden text-[15px] leading-none font-bold tracking-tight sm:inline">
              Checkweigher <span className="font-medium opacity-70">QA</span>
            </span>
          </NavLink>
          <span className="hidden h-6 w-px bg-white/20 sm:block" />
          <nav className="flex min-w-0 flex-1 items-center overflow-x-auto">
            <Tab to="/" end>
              Overview
            </Tab>
            <MachineTabs />
          </nav>
          <div className="flex shrink-0 items-center gap-2">
            <ThemeSwitch />
            <FullscreenButton />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-4 md:px-6">
        <Outlet />
      </main>
    </div>
  )
}
