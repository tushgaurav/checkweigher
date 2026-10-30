"""Detect missed serial lines from the indicator's 5-digit running number.

TD/US (feeding error) lines carry ``*****`` instead of a number. Whether the
indicator advances the counter for them is unknown, so a jump is only flagged
as a gap when it exceeds the number of unnumbered lines seen in between.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WRAP = 100_000
WRAP_WINDOW = 1_000


@dataclass(frozen=True)
class SeqEvent:
    kind: Literal["gap", "reset", "duplicate"]
    previous: int
    current: int
    missing: int = 0


class SequenceTracker:
    def __init__(self) -> None:
        self.last: int | None = None
        self._unnumbered = 0

    def observe(self, seq: int | None) -> SeqEvent | None:
        if seq is None:
            self._unnumbered += 1
            return None
        prev, unnumbered = self.last, self._unnumbered
        self.last, self._unnumbered = seq, 0
        if prev is None:
            return None
        if seq == prev:
            return SeqEvent("duplicate", prev, seq)
        wrapped = seq < prev and prev >= WRAP - WRAP_WINDOW and seq < WRAP_WINDOW
        if seq < prev and not wrapped:
            # Counter went backwards: summary cleared on the indicator.
            return SeqEvent("reset", prev, seq)
        missing = (seq - prev) % WRAP - 1 - unnumbered
        return SeqEvent("gap", prev, seq, missing) if missing > 0 else None
