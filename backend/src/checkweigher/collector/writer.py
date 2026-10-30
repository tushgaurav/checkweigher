"""Batched, idempotent weighing inserts with an on-disk spool for database outages."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from checkweigher.collector.models import WeighingRecord

log = logging.getLogger("cw.writer")

INSERT_SQL = (
    "INSERT INTO weighing (ts, machine_id, seq, judgement, weight_g, target_g, product_id, shift_date, "
    "shift_code, source, raw) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (machine_id, ts) DO NOTHING"
)


class WeighingWriter:
    def __init__(self, pool: AsyncConnectionPool, spool_dir: str, batch_size: int = 200,
                 flush_interval_s: float = 0.5):
        self.pool = pool
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.spool_path = Path(spool_dir) / "weighing.jsonl"
        self.spool_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue: asyncio.Queue[WeighingRecord] = asyncio.Queue()
        self.written = 0

    def put(self, rec: WeighingRecord) -> None:
        self.queue.put_nowait(rec)

    async def _insert(self, batch: list[WeighingRecord]) -> None:
        async with self.pool.connection() as conn, conn.transaction():
            async with conn.cursor() as cur:
                await cur.executemany(INSERT_SQL, [r.as_row() for r in batch])

    def _spool(self, batch: list[WeighingRecord]) -> None:
        with self.spool_path.open("a", encoding="utf-8") as f:
            for r in batch:
                f.write(json.dumps(r.to_json()) + "\n")
            f.flush()
            os.fsync(f.fileno())

    async def _flush(self, batch: list[WeighingRecord]) -> None:
        try:
            await self._insert(batch)
            self.written += len(batch)
        except Exception as e:
            log.warning("insert of %d records failed (%s); spooling to %s", len(batch), e, self.spool_path)
            await asyncio.to_thread(self._spool, batch)

    async def run(self) -> None:
        while True:
            batch = [await self.queue.get()]
            deadline = asyncio.get_running_loop().time() + self.flush_interval_s
            while len(batch) < self.batch_size:
                timeout = deadline - asyncio.get_running_loop().time()
                if timeout <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self.queue.get(), timeout))
                except TimeoutError:
                    break
            await self._flush(batch)

    async def replay_spool_forever(self, interval_s: float = 15.0) -> None:
        while True:
            await asyncio.sleep(interval_s)
            await self.replay_spool()

    async def replay_spool(self) -> None:
        if not self.spool_path.exists():
            return
        replaying = self.spool_path.with_suffix(".replaying")
        if not replaying.exists():
            self.spool_path.replace(replaying)
        lines = replaying.read_text(encoding="utf-8").splitlines()
        records = [WeighingRecord.from_json(json.loads(line)) for line in lines if line.strip()]
        try:
            for i in range(0, len(records), 1000):
                await self._insert(records[i : i + 1000])
        except Exception as e:
            log.info("spool replay deferred (%s); %d records pending", e, len(records))
            return
        replaying.unlink()
        self.written += len(records)
        log.info("replayed %d spooled records", len(records))

    async def drain(self) -> None:
        batch: list[WeighingRecord] = []
        while not self.queue.empty():
            batch.append(self.queue.get_nowait())
        if batch:
            await self._flush(batch)
