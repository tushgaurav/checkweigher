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
  addresses, wire offset = address - 1). Addresses match manual Tables 18/19 (PDF:
  https://aandd.jp/products/manual/indicators/1WMPD4003953A_AD4412_4413-CW.pdf). "Low word first" comes only from the
  §10.3.1 example, which itself uses an older map (total at address 45, not 190), so word order is unproven. Value
  encoding of decimal registers is NOT stated: `value_encoding` (scaled_int | float32) and `word_order` are
  per-machine config - verify on site. IR 1-4 hold the indicator's own IP (identity check), IR 23-28 its RS-232C
  settings. RS-232C factory default is 2400 baud 7N1 (manual §9 defaults table); the collector default is 9600 8N1.
- Site 1 (2026-11-05, AD-4412-CW at 192.168.0.1, Modbus TCP slave 1): firmware differs from the manual. Its RS-232C
  menu is Serial Mode / Output Format ("Weight Data Only") / Output Preset Tare / Output 2nd header + baud/parity/
  data/stop (screen: Disable, 115200 8N1). Modbus confirms: IR 23-30 and IR 31-38 are 8-field RS-232C / RS-485 blocks
  (manual: 6 fields), so later addresses shift (IR 39 = 2 Modbus TCP, IR 40 = 1 slave address). Decoded from the dump,
  low word first, scaled integers: All summary starts at IR 216 (total, OK, HiHi, Hi, Lo, LoLo, TD, US, foreign, then
  4 counters not in the manual at 234-240), total weight 242, average 244, max 246, min 248, range 250, SD 252
  (2 decimals), CV 254 (16-bit, 2 decimals); OK summary 255-269 (count, total weight, avg, max, min, range, SD, CV);
  sample summary from 270, OK sample summary from 309. Cross-checks hold (total = sum, range = max - min,
  CV = SD / mean). A before/after dump around 10 Hi products confirmed the counters (total +10, Hi +10). IR 214 went
  0 -> 222.6 g (the last product): last weighing result OR live weight - unverified. HR 1-1000 holds no product
  settings (non-zero values match DI settings in Table 19), so target/limits are not readable over Modbus there.
  Serial: Output Format offers Cyclic Print; Serial Mode lists Disable / Summary / Stream / Weighing Result & Summary.
- Block addresses are per-machine config (`modbus.summary_address`, `weighing_result_address`,
  `product_settings_address`, null = not available, plus `decimals` when product settings are unreadable) ->
  `registers.Layout`. Decoding always uses the manual's field order inside a block. The simulator (`--summary-address`
  etc.) and `probe.py modbus` take the same options.
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
- `scripts/probe.py` (run with `uv run --no-sync python ../scripts/probe.py ports|serial|serial-scan|modbus ...` from
  `backend/`) is the read-only on-site probe: timestamped serial capture with hex + parse result, baud/format scan, and
  Modbus dumps decoded with every word order x value encoding (`--watch` for counter deltas, `--out` to log). Use it to
  settle the open device questions (encoding, word order, absolute vs offset limits, TD/US numbering) before
  editing `config.yaml`. Works against the simulator (`socket://127.0.0.1:7001`, `modbus 127.0.0.1 --port 5020`).

## Verification

```bash
cd backend && uv run --no-sync ruff check src tests && uv run --no-sync pytest -q   # DB tests need the dev server
cd web && npx tsc -b && npx oxlint src/lib src/pages src/components/*.tsx && npm run build
```

## Dependency policy

- Python: `[tool.uv] exclude-newer` in `backend/pyproject.toml` blocks packages younger than 7 days; move the date forward deliberately.
- npm: install with `npm_config_before=<date 7 days ago>`; `openapi-typescript` runs via npx (its peer range excludes TS 6).
