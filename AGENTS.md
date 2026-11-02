# Checkweigher Dashboard

Web dashboard for A&D AD-4412-CW / AD-4413-CW checkweigher indicators (manual 1WMPD4003953A).
Target deployment: a Raspberry Pi (or any small Linux box) on site running everything via Docker Compose.

## Architecture

```
indicator ──RS-232C "Weighing Result / Cyclic Print"──> collector ──> PostgreSQL + TimescaleDB ──> API ──> React dashboard
          ──Modbus TCP (read-only)──────────────────────┘   (spool file if DB is down)          (FastAPI, also serves the SPA)
```

- `backend/` - one Python package (`checkweigher`, uv) with four entry points:
  - `cw-collector` - one worker per machine. Serial lines give every product (seq, judgement, weight);
    Modbus gives product settings (target/limits) and summary counters for reconciliation. `mode: modbus`
    derives exact counts from counter deltas but only sampled weights. Records are batched with an
    idempotent insert keyed on `(machine_id, ts)`; failed batches go to `var/spool/weighing.jsonl` and are replayed.
  - `cw-api` - FastAPI. KPI maths lives only in `api/kpi.py` (EGA definition etc. are placeholders pending
    client confirmation). All aggregates are sums of sufficient statistics -> exactly volume-weighted.
  - `cw-migrate` - applies `db/sql/*.sql`. `NNN_x.timescale.sql` / `NNN_x.plain.sql` are variants: hypertable +
    continuous aggregates when TimescaleDB is loadable, ordinary views otherwise (dev/tests). Keep their SELECT
    lists identical.
  - `cw-sim` - simulated indicator (`run`: serial-over-TCP on :7001 + Modbus TCP on :5020; `seed`: synthetic history).
- Device knowledge: `device/protocol.py` (serial line format), `device/registers.py` (Modbus map, 1-based manual
  addresses, wire offset = address - 1, low word first per manual §10.3.1). Value encoding of decimal registers is
  NOT stated in the manual: `value_encoding` (scaled_int | float32) and `word_order` are per-machine config - verify on site.
- Rows are filtered by stored production date + shift (`shift_date`, `shift_code`); a night shift crossing midnight
  belongs to the date it started. 15-minute aggregate buckets keep IST (UTC+5:30) hours aligned.
- `web/` - React 19 + Vite 8 + Tailwind 4 + shadcn (radix, "lyra" style) + TanStack Query + Recharts. Filters live
  in URL search params. `src/lib/api-types.ts` is generated from the API's OpenAPI schema (`npm run gen:api`).
  Single EventSource (`/api/live`) for machine status + new weighings.
  Light theme is the default; the header switch toggles `.dark` on `<html>` (persisted in localStorage `cw-theme`,
  applied pre-paint by the inline script in `index.html`). All colours are CSS vars in `src/index.css` (`--brand` =
  header bar, judgement tones `--ok/--over/--under/--feed/--reject`, `--signal` = target/EGA). Chart legends and
  limit-line definitions live in `src/lib/series.ts`; every dashboard card is a `Panel` (title, data-scope subtitle,
  CSV / full-screen tools, legend + stats footer).
- `deploy/` - Dockerfile (multi-arch) + docker-compose.yml (timescaledb:2.31.0-pg17, migrate, collector, api).

## Local development (Windows, no Docker)

```powershell
.\scripts\dev-db.ps1 init          # portable PostgreSQL 17 on localhost:5433 (+TimescaleDB if the zip is present)
cd backend; uv sync
uv run --no-sync python -m checkweigher.db.migrate
uv run --no-sync python -m checkweigher.simulator seed --days 7      # optional history
uv run --no-sync python -m checkweigher.simulator run --ppm 90 --drop-rate 0.01 --product-change-min 20
uv run --no-sync python -m checkweigher.collector
uv run --no-sync python -m checkweigher.api --port 8000
cd ..\web; npm install; npm run dev                                  # http://localhost:5173 (proxies /api)
```

- Prefer `python -m checkweigher.<x>` over the `cw-*.exe` shims while services run: uv cannot reinstall the
  package (e.g. after a pyproject change) while a shim is locked by a running process.
- psycopg async needs a selector event loop on Windows; entry points pass `loop_factory=asyncio.SelectorEventLoop`.
- `scripts/screenshot.py` (run with `uv run --no-sync --with playwright python ../scripts/screenshot.py URL out.png`
  from `backend/`) screenshots pages with the installed Chrome and prints console errors + API timings.

## Verification

```bash
cd backend && uv run --no-sync ruff check src tests && uv run --no-sync pytest -q   # DB tests need the dev server
cd web && npx tsc -b && npx oxlint src/lib src/pages src/components/*.tsx && npm run build
```

## Dependency policy

- Python: `[tool.uv] exclude-newer` in `backend/pyproject.toml` blocks packages younger than 7 days; move the date forward deliberately.
- npm: install with `npm_config_before=<date 7 days ago>`; `openapi-typescript` runs via npx (its peer range excludes TS 6).
