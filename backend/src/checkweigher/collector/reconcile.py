"""Cross-check serially received records against the indicator's Modbus counters."""

from __future__ import annotations

from collections import Counter as Tally
from dataclasses import dataclass
from datetime import datetime

from checkweigher.device.registers import Counters


@dataclass(frozen=True)
class ReconcileWindow:
    start: datetime
    end: datetime
    expected: int
    received: int
    expected_by_judgement: dict[str, int]
    received_by_judgement: dict[str, int]


class Reconciler:
    def __init__(self) -> None:
        self._baseline: Counters | None = None
        self._since: datetime | None = None
        self._received: Tally[str] = Tally()

    def on_record(self, judgement: str) -> None:
        if self._baseline is not None:
            self._received[judgement] += 1

    def check(self, counters: Counters, now: datetime) -> tuple[ReconcileWindow | None, bool]:
        """Returns (closed window or None, whether the indicator summary was cleared)."""
        base, since = self._baseline, self._since
        cleared = base is not None and counters.total < base.total
        window = None
        if base is not None and since is not None and not cleared:
            exp = {k: max(0, v - base.by_judgement()[k]) for k, v in counters.by_judgement().items()}
            window = ReconcileWindow(
                start=since,
                end=now,
                expected=counters.total - base.total,
                received=sum(self._received.values()),
                expected_by_judgement={k: v for k, v in exp.items() if v},
                received_by_judgement=dict(self._received),
            )
        self._baseline, self._since, self._received = counters, now, Tally()
        return window, cleared
