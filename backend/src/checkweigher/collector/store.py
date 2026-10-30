"""Collector-side database operations (everything except the weighing batch writer)."""

from __future__ import annotations

import json
import logging
from typing import Any

from psycopg_pool import AsyncConnectionPool

from checkweigher.collector.models import ProductContext
from checkweigher.collector.reconcile import ReconcileWindow
from checkweigher.config import MachineConfig, ShiftConfig
from checkweigher.shifts import Shift

log = logging.getLogger("cw.store")


class Store:
    def __init__(self, pool: AsyncConnectionPool):
        self.pool = pool

    async def sync_machines(self, machines: list[MachineConfig]) -> None:
        async with self.pool.connection() as conn:
            for m in machines:
                await conn.execute(
                    "INSERT INTO machine (id, code, name, mode) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET code = EXCLUDED.code, name = EXCLUDED.name, "
                    "mode = EXCLUDED.mode, active = true, updated_at = now()",
                    (m.id, m.code, m.name, m.mode),
                )

    async def sync_shifts(self, shifts: list[ShiftConfig]) -> None:
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute("DELETE FROM shift")
            for i, s in enumerate(shifts, start=1):
                await conn.execute(
                    "INSERT INTO shift (code, name, start_time, end_time, sort) VALUES (%s, %s, %s, %s, %s)",
                    (s.code, s.name, s.start, s.end, i),
                )

    async def load_shifts(self) -> list[Shift]:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT code, name, start_time, end_time, sort FROM shift ORDER BY sort")
            return [Shift(r["code"], r["name"], r["start_time"], r["end_time"], r["sort"])
                    for r in await cur.fetchall()]

    async def upsert_product(self, machine_id: int, ctx: ProductContext) -> int:
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "INSERT INTO product_setting (machine_id, group_no, product_no, target_g, hihi_g, hi_g, lo_g, "
                "lolo_g, tare_g, ow_exception, reject_stage) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (machine_id, group_no, product_no, target_g, hihi_g, hi_g, lo_g, lolo_g, tare_g, "
                "ow_exception, reject_stage) DO UPDATE SET last_seen = now() RETURNING id",
                (machine_id, ctx.group_no, ctx.product_no, ctx.target_g, ctx.hihi_g, ctx.hi_g, ctx.lo_g,
                 ctx.lolo_g, ctx.tare_g, ctx.ow_exception, ctx.reject_stage),
            )
            row = await cur.fetchone()
            assert row is not None
            return row["id"]

    async def event(self, machine_id: int | None, kind: str, message: str, detail: dict | None = None) -> None:
        log.info("event %s machine=%s: %s", kind, machine_id, message)
        try:
            async with self.pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO collector_event (machine_id, kind, message, detail) VALUES (%s, %s, %s, %s)",
                    (machine_id, kind, message, json.dumps(detail) if detail else None),
                )
        except Exception as e:
            log.warning("could not store event %s (%s)", kind, e)

    async def reconciliation(self, machine_id: int, w: ReconcileWindow, shift_date, shift_code: str) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO reconciliation (machine_id, window_start, window_end, shift_date, shift_code, "
                "expected, received, detail) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (machine_id, w.start, w.end, shift_date, shift_code, w.expected, w.received,
                 json.dumps({"expected": w.expected_by_judgement, "received": w.received_by_judgement})),
            )

    async def upsert_status(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        cols = ["machine_id", "serial_state", "modbus_state", "last_line_at", "last_modbus_at", "last_ts",
                "last_weight_g", "last_judgement", "last_seq", "product_id", "device_counters"]
        sql = (
            f"INSERT INTO machine_status ({', '.join(cols)}, updated_at) "
            f"VALUES ({', '.join(['%s'] * len(cols))}, now()) ON CONFLICT (machine_id) DO UPDATE SET "
            + ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[1:]) + ", updated_at = now()"
        )
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(sql, [
                    tuple(json.dumps(r[c]) if c == "device_counters" and r[c] is not None else r[c] for c in cols)
                    for r in rows
                ])
