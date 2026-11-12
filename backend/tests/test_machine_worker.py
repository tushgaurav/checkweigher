import asyncio
from datetime import UTC, date, datetime, timedelta

from checkweigher.collector.machine import MachineWorker
from checkweigher.config import MachineConfig


class FakeWriter:
    def __init__(self) -> None:
        self.records = []

    def put(self, rec) -> None:
        self.records.append(rec)


class FakeStore:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def event(self, machine_id, kind, message, detail=None) -> None:
        self.events.append(kind)


def serial_worker() -> tuple[MachineWorker, FakeStore, FakeWriter]:
    cfg = MachineConfig.model_validate({"id": 1, "code": "CW-01", "name": "CW", "mode": "serial",
                                        "serial": {"url": "COM7"}})
    store, writer = FakeStore(), FakeWriter()
    return MachineWorker(cfg, store, writer, lambda ts: (date(2026, 11, 12), "A")), store, writer  # type: ignore[arg-type]


async def test_repeated_result_lines_are_stored_once():
    # Site 1, 2026-11-12: line #69 arrived ~588k times and each copy was stored as a new pack.
    w, store, writer = serial_worker()
    t0 = datetime(2026, 11, 12, 6, 29, 9, tzinfo=UTC)
    lines = ["00068,OK,ST,+0000156.0 g", *["00069,OK,ST,+0000156.4 g"] * 1000, "00070,HI,ST,+0000170.0 g"]
    for i, line in enumerate(lines):
        w._on_serial_line(line, t0 + timedelta(milliseconds=i))
    await asyncio.sleep(0)
    assert [r.seq for r in writer.records] == [68, 69, 70]
    assert store.events.count("seq_duplicate") == 1


async def test_unnumbered_feeding_errors_are_not_deduplicated():
    w, _, writer = serial_worker()
    t0 = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
    for i, line in enumerate(["00001,OK,ST,+0000156.0 g", "*****,TD,**,**********  ", "*****,TD,**,**********  ",
                              "00004,OK,ST,+0000156.2 g"]):
        w._on_serial_line(line, t0 + timedelta(seconds=i))
    await asyncio.sleep(0)
    assert [r.judgement for r in writer.records] == ["OK", "TD", "TD", "OK"]
