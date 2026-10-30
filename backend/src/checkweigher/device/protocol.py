"""Serial "Weighing Result" output in "Cyclic Print" format (manual §9.25-9.27).

Each judged product produces one 24-character ASCII line + CR LF::

    00001,OK,ST,+00012.345 g
    |     |  |  |         └ unit (2 chars)
    |     |  |  └ weight (10 chars, signed)
    |     |  └ header: ST stable, US unstable, OL overload
    |     └ judgement
    └ running total number (5 digits)

Feeding errors carry no number/weight: ``*****,TD,**,**********``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Judgement codes in the serial output and their meaning (manual §9.25, Table 5).
JUDGEMENTS: dict[str, str] = {
    "OK": "Passed",
    "HH": "Over HiHi limit",
    "HI": "Over Hi limit (overweight)",
    "LO": "Under Lo limit (underweight)",
    "LL": "Under LoLo limit",
    "TD": "Detect two (product spacing too short)",
    "US": "Unsplit (product longer than set length)",
    "E1": "External NG 1",
    "E2": "External NG 2",
    "MD": "Metal / foreign matter detected",
}
OVERWEIGHT = frozenset({"HH", "HI"})
UNDERWEIGHT = frozenset({"LO", "LL"})
FEEDING_ERROR = frozenset({"TD", "US"})

UNIT_TO_GRAMS: dict[str, Decimal] = {"g": Decimal(1), "kg": Decimal(1000)}

_WEIGHT_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*([A-Za-z]*)\s*$")


class ParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResultLine:
    seq: int | None
    judgement: str
    header: str | None
    weight: Decimal | None
    unit: str | None
    raw: str

    def weight_grams(self, default_unit: str = "g") -> Decimal | None:
        if self.weight is None:
            return None
        unit = (self.unit or default_unit).lower()
        if unit not in UNIT_TO_GRAMS:
            raise ParseError(f"unsupported unit {unit!r} in {self.raw!r}")
        return self.weight * UNIT_TO_GRAMS[unit]


def _is_masked(s: str) -> bool:
    s = s.strip()
    return not s or set(s) == {"*"}


def parse_result_line(line: str) -> ResultLine:
    raw = line.rstrip("\r\n")
    parts = raw.split(",", 3)
    if len(parts) != 4:
        hint = " (is the port Output mode set to 'Cyclic Print'?)" if len(parts) == 2 else ""
        raise ParseError(f"expected 4 comma-separated fields, got {len(parts)}: {raw!r}{hint}")
    seq_s, judgement, header_s, data_s = parts

    if _is_masked(seq_s):
        seq = None
    elif seq_s.strip().isdigit():
        seq = int(seq_s)
    else:
        raise ParseError(f"bad total number {seq_s!r} in {raw!r}")

    judgement = judgement.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2}", judgement):
        raise ParseError(f"bad judgement {judgement!r} in {raw!r}")

    header = None if _is_masked(header_s) else header_s.strip().upper()
    weight: Decimal | None = None
    unit: str | None = None
    if header != "OL" and not _is_masked(data_s):
        m = _WEIGHT_RE.match(data_s)
        if not m:
            raise ParseError(f"bad weight field {data_s!r} in {raw!r}")
        try:
            weight = Decimal(m.group(1))
        except InvalidOperation as e:
            raise ParseError(f"bad weight {m.group(1)!r} in {raw!r}") from e
        unit = m.group(2) or None

    return ResultLine(seq=seq, judgement=judgement, header=header, weight=weight, unit=unit, raw=raw)


def format_result_line(seq: int | None, judgement: str, weight: Decimal | None, decimals: int,
                       unit: str = "g", header: str = "ST") -> str:
    """Inverse of :func:`parse_result_line` (used by the simulator and tests)."""
    if seq is None or weight is None:
        return f"*****,{judgement},**,**********  "
    return f"{seq % 100000:05d},{judgement},{header},{weight:+0{10}.{decimals}f}{unit:>2}"
