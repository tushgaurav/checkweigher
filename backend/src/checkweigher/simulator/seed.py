"""Write synthetic historical weighings straight into the database (dashboard development)."""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime, timedelta

import psycopg

from checkweigher.collector.models import ProductContext
from checkweigher.config import AppConfig
from checkweigher.device.registers import ProductSettings
from checkweigher.shifts import Shift, ShiftResolver
from checkweigher.simulator.device import DEFAULT_PRODUCTS, SimIndicator, SimProduct

log = logging.getLogger("cw.sim.seed")

COLUMNS = ("ts", "machine_id", "seq", "judgement", "weight_g", "target_g", "product_id", "shift_date",
           "shift_code", "source", "raw")


def _settings(p: SimProduct) -> ProductSettings:
    return ProductSettings(p.group_no, p.product_no, p.decimal_point, p.target, p.hihi, p.hi, p.lo, p.lolo,
                           p.tare, p.ow_exception, p.reject_stage)


def seed(cfg: AppConfig, days: int, ppm: float, seed_value: int | None = None) -> int:
    rng = random.Random(seed_value)
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)
    total = 0
    with psycopg.connect(cfg.database.url, autocommit=True) as conn:
        shifts = [Shift(r[0], r[1], r[2], r[3], r[4]) for r in
                  conn.execute("SELECT code, name, start_time, end_time, sort FROM shift ORDER BY sort")]
        resolver = ShiftResolver(shifts, cfg.plant.tz)
        for m in cfg.machines:
            conn.execute(
                "INSERT INTO machine (id, code, name, mode) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (m.id, m.code, m.name, m.mode),
            )
            conn.execute("DELETE FROM weighing WHERE machine_id = %s AND ts >= %s AND ts < %s",
                         (m.id, start, end))
            sim = SimIndicator(DEFAULT_PRODUCTS[0], seed=rng.randrange(1 << 30))
            # Register products up front: the connection cannot run other statements during COPY.
            products: dict[SimProduct, int] = {}
            for p in DEFAULT_PRODUCTS:
                ctx = ProductContext.from_settings(_settings(p), "g")
                products[p] = conn.execute(
                    "INSERT INTO product_setting (machine_id, group_no, product_no, target_g, hihi_g, hi_g, "
                    "lo_g, lolo_g, tare_g, ow_exception, reject_stage, first_seen) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (machine_id, group_no, "
                    "product_no, target_g, hihi_g, hi_g, lo_g, lolo_g, tare_g, ow_exception, reject_stage) "
                    "DO UPDATE SET last_seen = now() RETURNING id",
                    (m.id, ctx.group_no, ctx.product_no, ctx.target_g, ctx.hihi_g, ctx.hi_g, ctx.lo_g,
                     ctx.lolo_g, ctx.tare_g, ctx.ow_exception, ctx.reject_stage, start),
                ).fetchone()[0]  # type: ignore[index]

            t = start
            stopped_until = start
            with conn.cursor().copy(f"COPY weighing ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                while t < end:
                    t += timedelta(seconds=rng.expovariate(ppm / 60.0) * 0.5 + 30.0 / ppm)
                    if t < stopped_until:
                        continue
                    if rng.random() < 1 / 4000:  # breakdowns / breaks of 5-40 minutes
                        stopped_until = t + timedelta(minutes=rng.uniform(5, 40))
                        continue
                    if rng.random() < 1 / 30000:  # occasional product change
                        sim.product = rng.choice(DEFAULT_PRODUCTS)
                    piece = sim.next_piece((t - start).total_seconds())
                    seq = sim.counters["total"] % 100000 if piece.weight is not None else None
                    shift_date, shift_code = resolver.resolve(t)
                    copy.write_row((t, m.id, seq, piece.judgement, piece.weight, sim.product.target,
                                    products[sim.product], shift_date, shift_code, "serial", piece.line))
                    total += 1
            log.info("machine %s: seeded %s -> %s", m.code, start, end)
        if conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'").fetchone():
            for view in ("weighing_15m", "weighing_hist"):
                conn.execute(f"CALL refresh_continuous_aggregate('{view}', NULL, NULL)")
    return total
