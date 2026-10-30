"""Derive per-product records from fast Modbus polling (no serial link).

The indicator's counters are exact even when a poll misses products, so every
counted product becomes a record with the right judgement. Only the latest
weight is available (input register 282); it is attached to one record when it
is consistent with that record's judgement, otherwise weights stay NULL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from checkweigher.collector.models import ProductContext
from checkweigher.device.registers import Counters

WEIGHED = frozenset({"OK", "HH", "HI", "LO", "LL", "MD"})
UNKNOWN = "??"


@dataclass
class DerivedPieces:
    pieces: list[tuple[str, Decimal | None]] = field(default_factory=list)
    reset: bool = False
    missed_weights: int = 0


class CounterDeltaTracker:
    def __init__(self) -> None:
        self.prev: Counters | None = None

    def update(self, c: Counters, last_weight_g: Decimal | None, ctx: ProductContext | None) -> DerivedPieces:
        prev, self.prev = self.prev, c
        if prev is None:
            return DerivedPieces()
        if c.total < prev.total:
            return DerivedPieces(reset=True)
        delta = c.total - prev.total
        if delta == 0:
            return DerivedPieces()

        judgements: list[str] = []
        before = prev.by_judgement()
        for code, now in c.by_judgement().items():
            judgements += [code] * max(0, now - before[code])
        judgements = judgements[:delta] + [UNKNOWN] * max(0, delta - len(judgements))

        weight_j = ctx.judge(last_weight_g) if (ctx and last_weight_g is not None) else None
        attach_to = None
        if last_weight_g is not None:
            if weight_j is not None and weight_j in judgements:
                attach_to = judgements.index(weight_j)
            elif weight_j is None and delta == 1 and judgements[0] in WEIGHED:
                attach_to = 0
            if attach_to is None and "MD" in judgements and weight_j in ("OK", "HH", "HI", "LO", "LL"):
                attach_to = judgements.index("MD")

        # Weighed record (if any) last: it is the most recent product.
        if attach_to is not None:
            judgements.append(judgements.pop(attach_to))
        pieces: list[tuple[str, Decimal | None]] = [(j, None) for j in judgements]
        if attach_to is not None:
            pieces[-1] = (pieces[-1][0], last_weight_g)
        missed = sum(1 for j, w in pieces if j in WEIGHED and w is None)
        return DerivedPieces(pieces=pieces, missed_weights=missed)
