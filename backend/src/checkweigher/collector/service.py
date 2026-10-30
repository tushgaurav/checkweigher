from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import date, datetime
from typing import Any

from checkweigher.collector.machine import MachineWorker
from checkweigher.collector.store import Store
from checkweigher.collector.writer import WeighingWriter
from checkweigher.config import AppConfig
from checkweigher.db.pool import open_pool
from checkweigher.shifts import DEFAULT_SHIFTS, Shift, ShiftResolver

log = logging.getLogger("cw.collector")


async def supervise(name: str, factory: Callable[[], Coroutine[Any, Any, Any]], restart_delay_s: float = 5.0) -> None:
    """Run a long-lived task forever: an unexpected error in one machine worker or loop must never
    take down data collection for the others."""
    while True:
        try:
            await factory()
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s crashed; restarting in %.0fs", name, restart_delay_s)
            await asyncio.sleep(restart_delay_s)


class CollectorService:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        shifts = [Shift(s.code, s.name, s.start, s.end, i) for i, s in enumerate(cfg.shifts or [], 1)]
        self.resolver = ShiftResolver(shifts or DEFAULT_SHIFTS, cfg.plant.tz)
        self.workers: list[MachineWorker] = []

    def resolve_shift(self, ts: datetime) -> tuple[date, str]:
        return self.resolver.resolve(ts)

    async def _sync_db(self, store: Store) -> None:
        """Push machine/shift config into the database; retried until it succeeds."""
        delay = 2.0
        while True:
            try:
                await store.sync_machines(self.cfg.machines)
                if self.cfg.shifts:
                    await store.sync_shifts(self.cfg.shifts)
                self.resolver = ShiftResolver(await store.load_shifts() or DEFAULT_SHIFTS, self.cfg.plant.tz)
                await store.event(None, "collector_started",
                                  f"collector started with {len(self.cfg.machines)} machine(s)")
                return
            except Exception as e:
                log.warning("database not ready (%s); collecting to spool, retrying in %.0fs", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)

    async def _refresh_shifts(self, store: Store) -> None:
        while True:
            await asyncio.sleep(300)
            try:
                if shifts := await store.load_shifts():
                    self.resolver = ShiftResolver(shifts, self.cfg.plant.tz)
            except Exception as e:
                log.warning("shift refresh failed: %s", e)

    async def _status_loop(self, store: Store) -> None:
        while True:
            await asyncio.sleep(self.cfg.collector.status_interval_s)
            try:
                await store.upsert_status([w.status_row() for w in self.workers])
            except Exception as e:
                log.debug("status update failed: %s", e)

    async def run(self) -> None:
        if not self.cfg.machines:
            raise SystemExit("no machines configured")
        # Short connection wait: during a database outage records must reach the spool quickly.
        pool = await open_pool(self.cfg.database.url, min_size=1, max_size=4, name="collector",
                               getconn_timeout_s=5.0)
        store = Store(pool)
        c = self.cfg.collector
        writer = WeighingWriter(pool, c.spool_dir, c.batch_size, c.flush_interval_s)
        self.workers = [MachineWorker(m, store, writer, self.resolve_shift) for m in self.cfg.machines]
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(supervise("db sync", lambda: self._sync_db(store)))
                tg.create_task(supervise("writer", writer.run))
                tg.create_task(supervise("spool replay", writer.replay_spool_forever))
                tg.create_task(supervise("status", lambda: self._status_loop(store)))
                tg.create_task(supervise("shift refresh", lambda: self._refresh_shifts(store)))
                for w in self.workers:
                    tg.create_task(supervise(f"machine {w.cfg.code}", w.run))
        finally:
            await writer.drain()
            await pool.close()
