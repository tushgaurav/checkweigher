"""One worker per checkweigher: serial result lines + Modbus context / counters."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from checkweigher.collector.modbus_only import CounterDeltaTracker
from checkweigher.collector.models import ProductContext, WeighingRecord
from checkweigher.collector.reconcile import Reconciler
from checkweigher.collector.sequence import SequenceTracker
from checkweigher.collector.serial_reader import SerialLineReader
from checkweigher.collector.store import Store
from checkweigher.collector.writer import WeighingWriter
from checkweigher.config import MachineConfig, ModbusConfig
from checkweigher.device import registers as R
from checkweigher.device.protocol import UNIT_TO_GRAMS, ParseError, parse_result_line

log = logging.getLogger("cw.machine")

ShiftFn = Callable[[datetime], tuple[date, str]]
ONE_US = timedelta(microseconds=1)
CONTEXT_WAIT_S = 10.0  # hold serial records at startup until product settings are known


class ModbusReadError(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class MachineWorker:
    def __init__(self, cfg: MachineConfig, store: Store, writer: WeighingWriter, resolve_shift: ShiftFn):
        self.cfg, self.store, self.writer, self.resolve_shift = cfg, store, writer, resolve_shift
        self.ctx: ProductContext | None = None
        self.decimal_point: int | None = None
        self.seq = SequenceTracker()
        self.reconciler = Reconciler()
        self.deltas = CounterDeltaTracker()
        self.serial_state = "connecting" if cfg.uses_serial else "disabled"
        self.modbus_state = "connecting" if cfg.uses_modbus else "disabled"
        self.last_line_at: datetime | None = None
        self.last_modbus_at: datetime | None = None
        self.last_record: WeighingRecord | None = None
        self.device_counters: dict | None = None
        self._last_ts: datetime | None = None
        self._parse_errors = 0
        self._parse_error_reported = 0.0
        self._serial: SerialLineReader | None = None
        self._bg: set[asyncio.Task] = set()
        self._pending: list[WeighingRecord] = []
        self._context_deadline = time.monotonic() + CONTEXT_WAIT_S if cfg.uses_modbus else 0.0

    # ---- helpers ---------------------------------------------------------------------------------
    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)

    def _event(self, kind: str, message: str, detail: dict | None = None) -> None:
        self._spawn(self.store.event(self.cfg.id, kind, message, detail))

    def _record(self, ts: datetime, seq: int | None, judgement: str, weight_g: Decimal | None, source: str,
                raw: str | None = None) -> WeighingRecord:
        # (machine_id, ts) is the idempotency key: keep timestamps strictly increasing per machine.
        if self._last_ts is not None and ts <= self._last_ts:
            ts = self._last_ts + ONE_US
        self._last_ts = ts
        shift_date, shift_code = self.resolve_shift(ts)
        ctx = self.ctx
        rec = WeighingRecord(
            ts=ts, machine_id=self.cfg.id, seq=seq, judgement=judgement, weight_g=weight_g,
            target_g=ctx.target_g if ctx else None, product_id=ctx.product_id if ctx else None,
            shift_date=shift_date, shift_code=shift_code, source=source, raw=raw,
        )
        self.last_record = rec
        if ctx is None and time.monotonic() < self._context_deadline:
            self._pending.append(rec)
        else:
            self._flush_pending()
            self.writer.put(rec)
        return rec

    def _flush_pending(self) -> None:
        ctx = self.ctx
        for rec in self._pending:
            if ctx is not None:
                rec.target_g, rec.product_id = ctx.target_g, ctx.product_id
            self.writer.put(rec)
        self._pending.clear()
        self._context_deadline = 0.0

    def status_row(self) -> dict:
        r = self.last_record
        return {
            "machine_id": self.cfg.id,
            "serial_state": self.serial_state,
            "modbus_state": self.modbus_state,
            "last_line_at": self.last_line_at,
            "last_modbus_at": self.last_modbus_at,
            "last_ts": r.ts if r else None,
            "last_weight_g": r.weight_g if r else None,
            "last_judgement": r.judgement if r else None,
            "last_seq": r.seq if r else None,
            "product_id": self.ctx.product_id if self.ctx else None,
            "device_counters": self.device_counters,
        }

    # ---- serial ----------------------------------------------------------------------------------
    def _on_serial_state(self, state: str, detail: str | None) -> None:
        if state != self.serial_state:
            self._event(f"serial_{state}", f"serial {state}" + (f": {detail}" if detail else ""))
        self.serial_state = state

    def _on_serial_line(self, text: str, ts: datetime) -> None:
        self.last_line_at = ts
        try:
            line = parse_result_line(text)
            weight_g = line.weight_grams(self.cfg.unit)
        except ParseError as e:
            self._parse_errors += 1
            now = time.monotonic()
            if now - self._parse_error_reported > 60:
                self._event("parse_error", str(e), {"count": self._parse_errors, "line": text})
                self._parse_error_reported, self._parse_errors = now, 0
            return
        if ev := self.seq.observe(line.seq):
            if ev.kind == "gap":
                self._event("seq_gap", f"{ev.missing} result line(s) missed between #{ev.previous} and "
                            f"#{ev.current}", asdict(ev))
            elif ev.kind == "reset":
                self._event("counter_reset", f"running number went from #{ev.previous} to #{ev.current} "
                            "(summary cleared?)", asdict(ev))
        self._record(ts, line.seq, line.judgement, weight_g, "serial", raw=text)
        self.reconciler.on_record(line.judgement)

    # ---- modbus ----------------------------------------------------------------------------------
    async def _read(self, client: AsyncModbusTcpClient, kind: str, address: int, count: int) -> R.Block:
        assert self.cfg.modbus is not None
        fn = client.read_holding_registers if kind == "hr" else client.read_input_registers
        rr = await fn(R.offset(address), count=count, device_id=self.cfg.modbus.device_id)
        if rr.isError():
            raise ModbusReadError(f"{kind} {address}+{count}: {rr}")
        self.last_modbus_at = utcnow()
        codec = R.Codec(self.cfg.modbus.word_order, self.cfg.modbus.value_encoding)
        return R.Block(address, list(rr.registers), codec)

    async def _read_context(self, client: AsyncModbusTcpClient) -> None:
        ids = await self._read(client, "hr", R.HR_PRODUCT_NO, 2)
        prod = await self._read(client, "hr", R.HR_PRODUCT_BLOCK_START, R.HR_PRODUCT_BLOCK_COUNT)
        settings = R.ProductSettings.from_blocks(ids, prod)
        self.decimal_point = settings.decimal_point
        ctx = ProductContext.from_settings(settings, self.cfg.unit)
        if self.ctx is not None and self.ctx.key() == ctx.key() and self.ctx.product_id is not None:
            return
        try:
            ctx = replace(ctx, product_id=await self.store.upsert_product(self.cfg.id, ctx))
        except Exception as e:
            log.warning("%s: could not store product settings (%s); retrying next poll", self.cfg.code, e)
        changed = self.ctx is None or self.ctx.key() != ctx.key()
        self.ctx = ctx
        self._flush_pending()
        if changed:
            self._event("product", f"product G{ctx.group_no}-P{ctx.product_no} target {ctx.target_g} g",
                        {"group_no": ctx.group_no, "product_no": ctx.product_no, "target_g": str(ctx.target_g),
                         "hi_g": str(ctx.hi_g), "lo_g": str(ctx.lo_g)})

    async def _read_counters(self, client: AsyncModbusTcpClient) -> tuple[R.Counters, R.Block]:
        block = await self._read(client, "ir", R.IR_BLOCK_START, R.IR_BLOCK_COUNT)
        counters = R.Counters.from_block(block)
        self.device_counters = asdict(counters)
        return counters, block

    async def _reconcile(self, client: AsyncModbusTcpClient) -> None:
        counters, _ = await self._read_counters(client)
        now = utcnow()
        window, cleared = self.reconciler.check(counters, now)
        if cleared:
            self._event("summary_cleared", "indicator summary counters were reset")
        if window and (window.expected or window.received):
            shift_date, shift_code = self.resolve_shift(window.end)
            try:
                await self.store.reconciliation(self.cfg.id, window, shift_date, shift_code)
            except Exception as e:
                # Dropping a whole window (expected and received) keeps completeness unbiased.
                log.warning("%s: could not store reconcile window (%s)", self.cfg.code, e)
            if window.received < window.expected:
                log.info("%s: received %d of %d products in reconcile window", self.cfg.code,
                         window.received, window.expected)

    async def _poll_modbus_only(self, client: AsyncModbusTcpClient) -> None:
        counters, block = await self._read_counters(client)
        weight_g = None
        if self.decimal_point is not None:
            weight_g = block.value(R.IR_WEIGHING_RESULT, self.decimal_point) * UNIT_TO_GRAMS[self.cfg.unit]
        result = self.deltas.update(counters, weight_g, self.ctx)
        if result.reset:
            self._event("summary_cleared", "indicator summary counters were reset")
        now = utcnow()
        for judgement, w in result.pieces:
            self._record(now, None, judgement, w, "modbus")

    async def _modbus_session(self, client: AsyncModbusTcpClient, mb: ModbusConfig) -> None:
        modbus_only = not self.cfg.uses_serial
        next_ctx = next_rec = 0.0
        loop = asyncio.get_running_loop()
        while True:
            now = loop.time()
            if now >= next_ctx:
                await self._read_context(client)
                next_ctx = now + mb.context_interval_s
            if modbus_only:
                await self._poll_modbus_only(client)
                await asyncio.sleep(mb.poll_interval_s)
                continue
            if now >= next_rec:
                await self._reconcile(client)
                next_rec = now + mb.reconcile_interval_s
            await asyncio.sleep(max(0.05, min(next_ctx, next_rec) - loop.time()))

    async def _modbus_loop(self) -> None:
        mb = self.cfg.modbus
        assert mb is not None
        backoff = 1.0
        while True:
            # reconnect_delay=0: reconnection is handled here, not by pymodbus.
            client = AsyncModbusTcpClient(mb.host, port=mb.port, timeout=mb.timeout_s, retries=1,
                                          reconnect_delay=0)
            try:
                if not await client.connect():
                    raise ModbusReadError(f"cannot connect to {mb.host}:{mb.port}")
                if self.modbus_state != "connected":
                    self._event("modbus_connected", f"modbus connected {mb.host}:{mb.port}")
                self.modbus_state = "connected"
                backoff = 1.0
                await self._modbus_session(client, mb)
            except (ModbusException, ModbusReadError, OSError, TimeoutError) as e:
                if self.modbus_state != "disconnected":
                    self._event("modbus_disconnected", f"modbus error: {e}")
                self.modbus_state = "disconnected"
            finally:
                client.close()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    # ---- lifecycle -------------------------------------------------------------------------------
    async def _release_pending_after_timeout(self) -> None:
        await asyncio.sleep(CONTEXT_WAIT_S)
        if self._pending:
            log.warning("%s: no product settings after %.0fs; storing records without target", self.cfg.code,
                        CONTEXT_WAIT_S)
            self._flush_pending()

    async def run(self) -> None:
        if self.cfg.uses_serial:
            assert self.cfg.serial is not None
            self._serial = SerialLineReader(self.cfg.serial, asyncio.get_running_loop(), self._on_serial_line,
                                            self._on_serial_state, self.cfg.code)
            self._serial.start()
        if self._context_deadline:
            self._spawn(self._release_pending_after_timeout())
        try:
            if self.cfg.uses_modbus:
                await self._modbus_loop()
            else:
                await asyncio.Event().wait()
        finally:
            if self._serial:
                await asyncio.to_thread(self._serial.stop)
            self._flush_pending()
